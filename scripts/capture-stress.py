#!/usr/bin/env python3
"""Record uninterrupted nested Hyprflow retarget/reversal sequences and their measured state."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
HELPER = runpy.run_path(str(ROOT / "scripts/nested-session.py"))
PROOF = runpy.run_path(str(ROOT / "scripts/capture-proof.py"))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class StressCapture:
    def __init__(self, args):
        self.state = HELPER["session"](args.directory)
        self.output = Path(args.output).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        require(not any(self.output.iterdir()), "Use an empty output directory to preserve prior receipts")
        self.artifact = Path(args.artifact).resolve()
        self.artifact_sha256 = hashlib.sha256(self.artifact.read_bytes()).hexdigest()
        require(not args.sha256 or self.artifact_sha256 == args.sha256, "Artifact differs from approved build")
        self.started = time.monotonic()
        self.recorder = None
        self.evidence = {"passed": False, "pid": self.state["pid"], "signature": self.state["signature"],
                         "artifact_sha256": self.artifact_sha256, "actions": [], "samples": [], "checks": []}

    def elapsed(self):
        return round(time.monotonic() - self.started, 6)

    def control(self, *args):
        return HELPER["control"](self.state, *args)

    def status(self):
        value = json.loads(self.control("repl", "return hl.plugin.hyprflow.status()").stdout)
        self.evidence["samples"].append({"seconds": self.elapsed(), "status": value})
        return value

    def workspace(self):
        return json.loads(self.control("-j", "activeworkspace").stdout)["id"]

    def save(self):
        (self.output / "manifest.json").write_text(json.dumps(self.evidence, indent=2) + "\n")

    def action(self, name, argument=None):
        value = "" if argument is None else json.dumps(argument)
        expression = ("local before = hl.plugin.hyprflow.status(); "
                      f"hl.plugin.hyprflow.{name}({value}); "
                      "return before .. '\\n' .. hl.plugin.hyprflow.status()")
        started = self.elapsed()
        before, after = map(json.loads, self.control("repl", expression).stdout.splitlines())
        self.evidence["actions"].append({"seconds": started, "completed_seconds": self.elapsed(),
                                        "action": name, "argument": argument, "before": before, "after": after})
        if before["open"] and after["open"]:
            require(before["position"] == after["position"], f"{name} snapped row position at retarget")
            require(before["openness"] == after["openness"], f"{name} snapped openness at reversal")
        self.save()

    def sample_for(self, duration):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            self.status()
            time.sleep(0.008)

    def settled(self, selected):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            value = self.status()
            if value.get("selected") == selected and not value.get("closing", True):
                if value.get("openness", 0) > 0.9999 and abs(value["position"] - (selected - 1)) < 0.0001:
                    return value
            time.sleep(0.008)
        raise RuntimeError(f"Selection {selected} did not settle: {value}")

    def closed(self, expected_workspace):
        deadline = time.monotonic() + 4
        openness = 1.0
        samples = 0
        while time.monotonic() < deadline:
            value = self.status()
            current = value.get("openness", 0.0)
            require(current <= openness + 0.000001, "Stable close reversed its openness trajectory")
            openness = current
            samples += 1
            if not value["open"]:
                require(self.workspace() == expected_workspace, "Close activated an unexpected workspace")
                self.evidence["checks"].append({"stable_close_monotonic": True, "samples": samples,
                                                "workspace": expected_workspace, "seconds": self.elapsed()})
                self.save()
                return
            time.sleep(0.008)
        raise RuntimeError(f"Flow did not close: {value}")

    def start_recording(self):
        require(not self.status()["open"], "Stress proof requires flow initially closed")
        self.control("dispatch", "hl.dsp.focus({ workspace = 4 })")
        entries = [line for line in Path(f'/proc/{self.state["pid"]}/maps').read_text().splitlines()
                   if line.split(maxsplit=5)[-1] == str(self.artifact)]
        require(entries and all(int(line.split()[4]) == self.artifact.stat().st_ino for line in entries),
                "Current artifact inode is not mapped into the owned compositor")
        self.evidence.update(version=self.control("version").stdout, mapped_artifact=entries,
                             monitors=json.loads(self.control("-j", "monitors").stdout))
        self.started = time.monotonic()
        with (self.output / "recorder.log").open("w") as log:
            self.recorder = subprocess.Popen(
                ["wf-recorder", "-o", "WAYLAND-1", "-r", "60", "-f", str(self.output / "stress.mp4")],
                env=HELPER["environment"](self.state), stdout=log, stderr=log,
            )
        self.sample_for(0.3)
        require(self.recorder.poll() is None, "Video recorder exited before the sequence")

    def run(self):
        self.start_recording()
        # Reverse twice before entry finishes, then let the original workspace settle.
        for _ in range(3):
            self.action("toggle")
            self.sample_for(0.075)
        self.settled(4)
        require(self.workspace() == 4, "Entry reversal switched the actual workspace")
        self.evidence["checks"].append({"entry_toggle_reversal": True})
        # Each new destination interrupts the previous flight; intermediate frames remain in the video.
        for selected in (1, 9, 3):
            self.action("jump", selected)
            self.sample_for(0.075)
        self.settled(3)
        require(self.workspace() == 4, "Rapid retarget switched the actual workspace")
        self.evidence["checks"].append({"rapid_retarget": [1, 9, 3], "selected": 3})
        self.action("accept")
        self.closed(3)
        self.sample_for(0.15)
        self.action("toggle")
        self.settled(3)
        for selected in (1, 9):
            self.action("jump", selected)
            self.sample_for(0.075)
        self.action("cancel")
        self.closed(3)
        self.evidence["checks"].append({"cancel_during_long_jump": True, "origin": 3})
        self.action("toggle")
        self.settled(3)
        for _ in range(3):
            self.action("toggle")
            self.sample_for(0.075)
        self.closed(3)
        self.evidence["checks"].append({"exit_toggle_reversal": True})
        self.sample_for(0.3)
        self.evidence["final_status"] = self.status()
        self.evidence["final_workspace"] = self.workspace()
        self.evidence["configerrors"] = self.control("configerrors").stdout.strip()
        require(not self.evidence["configerrors"], "Nested configuration has errors")
        require(hashlib.sha256(self.artifact.read_bytes()).hexdigest() == self.artifact_sha256,
                "Artifact changed while recording")

    def finish_recording(self):
        if self.recorder is None:
            return
        recorder, self.recorder = self.recorder, None
        PROOF["stop_recorder"](recorder, self.evidence)
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=width,height,avg_frame_rate,nb_frames",
             "-show_entries", "format=duration", "-of", "json", str(self.output / "stress.mp4")],
            text=True, capture_output=True, check=True, timeout=10,
        )
        self.evidence["video"] = json.loads(result.stdout)
        stream = self.evidence["video"]["streams"][0]
        numerator, denominator = map(float, stream["avg_frame_rate"].split("/"))
        require(numerator / denominator >= 55 and int(stream["nb_frames"]) >= 120,
                "Video lacks the expected frame cadence or duration")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("output")
    parser.add_argument("--artifact", default=str(ROOT / "build/hyprflow.so"))
    parser.add_argument("--sha256")
    proof = StressCapture(parser.parse_args())
    try:
        with HELPER["isolated_input"](proof.state) as receipt:
            proof.evidence["input_isolation"] = receipt
            proof.run()
            proof.finish_recording()
        proof.evidence["passed"] = True
    except Exception as error:
        proof.evidence["error"] = str(error)
        try:
            proof.finish_recording()
        except Exception as recorder_error:
            proof.evidence["recorder_error"] = str(recorder_error)
        raise
    finally:
        proof.save()
    print(proof.output / "manifest.json")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Capture real nested compositor frames and dispatcher/keyboard evidence for Hyprflow."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
HELPER = runpy.run_path(str(HERE / "nested-session.py"))
KEYBOARD = runpy.run_path(str(HERE / "nested-key.py"))


def capture(state, directory, name):
    path = directory / f"{name}.png"
    subprocess.run(["grim", "-o", "WAYLAND-1", str(path)], env=HELPER["environment"](state), check=True, timeout=10)
    return {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def status(state):
    return json.loads(HELPER["control"](state, "repl", "return hl.plugin.hyprflow.status()").stdout)


def verify_step(actual, selected, workspace, actual_workspace):
    if selected is None:
        assert actual == {"open": False}, f"Expected closed flow; got {actual}"
    else:
        assert actual["open"] and not actual["closing"], f"Expected settled open flow; got {actual}"
        assert actual["selected"] == selected, f"Expected selected {selected}; got {actual}"
        assert actual["openness"] > 0.999, f"Entry animation did not settle: {actual}"
        assert abs(actual["position"] - (selected - 1)) < 0.001, f"Navigation did not settle: {actual}"
    assert actual_workspace == workspace, f"Expected actual workspace {workspace}; got {actual_workspace}"


def wait_settled(state, selected, started):
    samples = []
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        actual = status(state)
        samples.append({"time": round(time.monotonic() - started, 4), "status": actual})
        if selected is None and not actual["open"]:
            return actual, samples
        if selected is not None and actual.get("selected") == selected and not actual.get("closing", True):
            if actual.get("openness", 0) > 0.999 and abs(actual["position"] - (selected - 1)) < 0.001:
                return actual, samples
        time.sleep(0.025)
    return actual, samples


def stop_recorder(recorder, evidence):
    if recorder is None:
        return
    recorder.send_signal(signal.SIGINT)
    try:
        recorder.wait(timeout=10)
    except subprocess.TimeoutExpired:
        evidence["recorder_timeout"] = True
        recorder.terminate()
        try:
            recorder.wait(timeout=3)
        except subprocess.TimeoutExpired:
            recorder.kill()
            recorder.wait(timeout=3)
        raise RuntimeError("Owned recorder failed to finalize within 10 seconds")
    if recorder.returncode:
        raise RuntimeError(f"Recorder exited with status {recorder.returncode}")


def record_sequence(state, args, evidence):
    output = Path(args.output).resolve()
    control = HELPER["control"]
    recorder = None
    if status(state)["open"]:
        control(state, "repl", "return hl.plugin.hyprflow.cancel()")
        closed, _ = wait_settled(state, None, time.monotonic())
        assert not closed["open"], "Could not close initial flow"
    for index in range(1, 8):
        control(state, "dispatch", f"hl.dsp.focus({{ workspace = {index} }})")
        time.sleep(0.3)
        evidence["frames"].append(capture(state, output, f"fixture-{index}"))
    try:
        if args.video:
            with (output / "recorder.log").open("w") as log:
                recorder = subprocess.Popen(
                    ["wf-recorder", "-o", "WAYLAND-1", "-r", "60", "-f", str(output / "navigation.mp4")],
                    env=HELPER["environment"](state), stdout=log, stderr=log,
                )
            time.sleep(0.3)
        control(state, "dispatch", "hl.dsp.focus({ workspace = 4 })")
        time.sleep(0.2)
        evidence["frames"].append(capture(state, output, "01-workspace"))
        actions = [("F10", "02-open", 4, 4), ("Right", "03-right", 5, 4), ("Left", "04-left", 4, 4),
                   ("7", "05-jump-seven", 7, 4), ("1", "06-jump-one", 1, 4), ("4", "07-jump-four", 4, 4),
                   ("7", "08-selected-seven", 7, 4), ("Return", "09-accepted", None, 7),
                   ("F10", "10-reopened", 7, 7), ("4", "11-before-cancel", 4, 7),
                   ("Escape", "12-cancelled", None, 7)]
        for key, name, selected, workspace in actions:
            before = status(state)
            started = time.monotonic()
            KEYBOARD["send_key"](args.directory, key)
            time.sleep(0.06)
            evidence["frames"].append(capture(state, output, name + "-transition"))
            after, samples = wait_settled(state, selected, started)
            actual_workspace = json.loads(control(state, "-j", "activeworkspace").stdout)["id"]
            evidence["actions"].append({"key": key, "before": before, "after": after,
                                        "elapsed_seconds": round(time.monotonic() - started, 4),
                                        "workspace": actual_workspace, "samples": samples})
            verify_step(after, selected, workspace, actual_workspace)
            evidence["frames"].append(capture(state, output, name))
        evidence["configerrors"] = control(state, "configerrors").stdout.strip()
        evidence["final_status"] = status(state)
        assert not evidence["configerrors"], "Nested compositor reports configuration errors"
    except Exception as error:
        evidence["error"] = str(error)
        raise
    finally:
        try:
            stop_recorder(recorder, evidence)
        except Exception as error:
            evidence["recorder_error"] = str(error)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="Nested session state directory")
    parser.add_argument("output", help="Empty proof output directory")
    parser.add_argument("--video", action="store_true", help="Record sequence with installed wf-recorder")
    parser.add_argument("--artifact", default=str(HERE.parent / "build/hyprflow.so"))
    parser.add_argument("--sha256", help="Expected SHA-256 of the approved plugin")
    args = parser.parse_args()
    state = HELPER["session"](args.directory)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    assert not any(output.iterdir()), "Use an empty output directory to preserve earlier receipts"
    artifact = Path(args.artifact).resolve()
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    evidence = {"passed": False, "pid": state["pid"], "signature": state["signature"],
                "artifact_sha256": digest, "frames": [], "actions": []}
    try:
        assert not args.sha256 or digest == args.sha256, "Artifact differs from approved build"
        mappings = [line for line in Path(f'/proc/{state["pid"]}/maps').read_text().splitlines()
                    if line.split(maxsplit=5)[-1] == str(artifact)]
        assert mappings and all(int(line.split()[4]) == artifact.stat().st_ino for line in mappings), "Artifact inode not mapped"
        evidence.update(mapped_artifact=mappings, version=HELPER["control"](state, "version").stdout,
                        plugins=HELPER["control"](state, "plugin", "list").stdout)
        with HELPER["isolated_input"](state) as receipt:
            evidence["input_isolation"] = receipt
            record_sequence(state, args, evidence)
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == digest, "Artifact changed during proof"
        evidence["passed"] = True
    except Exception as error:
        evidence.setdefault("error", str(error))
        raise
    finally:
        (output / "manifest.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(output / "manifest.json")


if __name__ == "__main__":
    main()

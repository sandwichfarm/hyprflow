#!/usr/bin/env python3
"""Verify lifecycle and transition behavior only inside an owned nested compositor."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
HELPER = runpy.run_path(str(ROOT / "scripts/nested-session.py"))
KEYBOARD = runpy.run_path(str(ROOT / "scripts/nested-key.py"))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LifecycleProof:
    def __init__(self, args):
        self.directory = args.directory
        self.state = HELPER["session"](args.directory)
        self.output = Path(args.output).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.artifact = Path(args.artifact).resolve()
        self.sha256 = digest(self.artifact)
        require(self.sha256 == args.sha256, "Artifact differs from the parent-approved build")
        self.started = time.monotonic()
        self.probe = None
        self.process = None
        self.original_focus = None
        self.input_log = self.output / "received.bin"
        self.evidence = {"passed": False, "pid": self.state["pid"], "start_time": self.state["start_time"],
                         "signature": self.state["signature"], "artifact": str(self.artifact),
                         "artifact_sha256": self.sha256, "checks": [], "samples": [], "keyboard_receipts": []}

    def control(self, *args, check=True):
        HELPER["session"](self.directory)
        return HELPER["control"](self.state, *args, check=check)

    def query(self, command):
        return json.loads(self.control("-j", command).stdout)

    def status(self):
        result = json.loads(self.control("repl", "return hl.plugin.hyprflow.status()").stdout)
        self.evidence["samples"].append({"seconds": round(time.monotonic() - self.started, 6), "status": result})
        return result

    def action(self, name, argument=None):
        value = "" if argument is None else json.dumps(argument)
        return self.control("repl", f"return hl.plugin.hyprflow.{name}({value})").stdout

    def wait(self, predicate, message, timeout=4):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            actual = self.status()
            if predicate(actual):
                return actual
            time.sleep(0.012)
        raise RuntimeError(f"{message}: {actual}")

    def settled(self, selected):
        def ready(value):
            if not value.get("open") or value.get("closing"):
                return False
            return (value["selected"] == selected and value["openness"] > .9999
                    and abs(value["position"] - (selected - 1)) < .0001)
        return self.wait(ready, f"Selection {selected} did not settle")

    def closed(self):
        return self.wait(lambda value: not value["open"], "Flow did not close")

    def record(self, name, **details):
        self.evidence["checks"].append({"name": name, "passed": True, **details})
        self.save()
        print(f"PASS {name}", flush=True)

    def save(self):
        (self.output / "manifest.json").write_text(json.dumps(self.evidence, indent=2) + "\n")

    def focus_probe(self):
        self.control("dispatch", "hl.dsp.focus({ workspace = 4 })")
        self.control("dispatch", f'hl.dsp.focus({{ window="address:{self.probe}" }})')

    def start_probe(self):
        require(not self.status()["open"], "Proof requires initially closed flow")
        self.control("dispatch", "hl.dsp.focus({ workspace = 4 })")
        self.original_focus = self.query("activewindow").get("address")
        self.initial_submap = self.control("submap").stdout.strip()
        self.input_log.write_bytes(b"")
        ready = self.input_log.with_suffix(".ready")
        ready.unlink(missing_ok=True)
        self.process = subprocess.Popen(
            ["kitty", "--config", "NONE", "--class", "hyprflow-lifecycle-probe", "-o", "confirm_os_window_close=0",
             "python3", str(ROOT / "scripts/input-fixture.py"), str(self.input_log)],
            env=HELPER["environment"](self.state), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            client = next((item for item in self.query("clients") if item["class"] == "hyprflow-lifecycle-probe"), None)
            if client and ready.exists():
                self.probe = client["address"]
                break
            time.sleep(.05)
        require(self.probe, "Lifecycle input probe did not become ready")
        self.focus_probe()
        self.keyboard_restored()
        self.evidence["version"] = self.control("version").stdout
        self.evidence["plugins_before"] = self.control("plugin", "list").stdout
        self.evidence["mapped_artifact"] = self.mapped_artifact()

    def mapped_artifact(self):
        entries = [line for line in Path(f'/proc/{self.state["pid"]}/maps').read_text().splitlines()
                   if line.split(maxsplit=5)[-1] == str(self.artifact)]
        require(entries, "Approved artifact is not mapped into the owned compositor")
        require(all(int(line.split()[4]) == self.artifact.stat().st_ino for line in entries), "Mapped artifact inode differs")
        require(digest(self.artifact) == self.sha256, "Artifact changed while verification ran")
        return entries

    def keyboard_restored(self):
        require(self.query("activewindow").get("address") == self.probe, "Compositor window focus was not restored")
        before = self.input_log.read_bytes()
        KEYBOARD["send_key"](self.directory, "Z")
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and self.input_log.read_bytes() == before:
            time.sleep(.01)
        received = self.input_log.read_bytes()[len(before):]
        # Kitty may encode the Z key using its CSI-u protocol instead of a literal byte.
        require(re.fullmatch(rb"(?:z|\x1b\[122(?:;\d+(?::[123])?)?u)+", received),
                f"Actual Z key did not return to the client: {received!r}")
        self.evidence["keyboard_receipts"].append({"seconds": round(time.monotonic() - self.started, 6),
                                                    "window": self.probe, "bytes_hex": received.hex()})

    def invalid_jump(self, opened):
        if opened:
            self.action("toggle")
            self.settled(4)
        before = self.status()
        result = self.control("repl", "local ok, err = pcall(function() return hl.plugin.hyprflow.jump('absent-lifecycle-target') end); "
                              "return tostring(ok) .. '\\n' .. tostring(err)").stdout
        after = self.status()
        require(result.startswith("false\n") and "absent" in result, f"Invalid jump did not return explicit error: {result!r}")
        require(after.get("selected") == before.get("selected") and after["open"] == before["open"], "Invalid jump changed selection")
        require(self.query("activeworkspace")["id"] == 4, "Invalid jump changed the actual workspace")
        self.record("invalid_jump_open" if opened else "invalid_jump_closed", before=before, after=after, error=result.strip())

    def boundaries_and_empty(self):
        for selected, direction in ((1, "left"), (9, "right")):
            self.action("jump", selected)
            self.settled(selected)
            self.control("repl", f"for i = 1, 4 do hl.plugin.hyprflow.{direction}() end; return hl.plugin.hyprflow.status()")
            actual = self.settled(selected)
            require(self.query("activeworkspace")["id"] == 4, "Boundary navigation switched the actual workspace")
            self.record(f"boundary_{direction}", status=actual)
        before = [item for item in self.query("workspaces") if item["id"] == 9]
        require(not any(item.get("windows", 0) for item in before), "Workspace 9 is not empty")
        self.action("accept")
        self.closed()
        active = self.query("activeworkspace")
        require(active["id"] == 9 and active["windows"] == 0, "Accept did not activate empty workspace 9")
        self.record("accept_empty_nine", existed_before=bool(before), active_workspace=active)
        self.action("toggle")
        self.settled(9)
        self.action("jump", 4)
        self.settled(4)
        self.action("cancel")
        self.closed()
        require(self.query("activeworkspace")["id"] == 9, "Cancel did not return to origin 9")
        self.record("cancel_preserves_origin_nine")
        self.focus_probe()

    def continuous_action(self, name, argument=None):
        value = "" if argument is None else json.dumps(argument)
        # Observe the action inside one callback: separate IPC requests can
        # straddle a render frame and confuse normal spring motion with a jump.
        expression = ("local before = hl.plugin.hyprflow.status(); "
                      f"hl.plugin.hyprflow.{name}({value}); "
                      "return before .. '\\n' .. hl.plugin.hyprflow.status()")
        started = time.monotonic()
        before, after = map(json.loads, self.control("repl", expression).stdout.splitlines())
        elapsed = time.monotonic() - started
        require(before["open"] and after["open"], "Retarget unexpectedly removed the flow")
        require(after["position"] == before["position"], "Focus teleported during retarget")
        require(after["openness"] == before["openness"], "Opening progress reset during retarget")
        return {"before": before, "after": after, "observation_seconds": round(elapsed, 6), "sampling": "atomic_lua_callback"}

    def reversals(self):
        self.action("toggle")
        self.settled(4)
        self.action("jump", 8)
        self.wait(lambda value: value["position"] > 3.3 and value["position"] < 6.8, "No intermediate jump position")
        reversal = self.continuous_action("jump", 2)
        self.settled(2)
        self.action("cancel")
        self.closed()
        require(self.query("activeworkspace")["id"] == 4, "Rapid reversal/cancel lost origin 4")
        self.record("rapid_reversal", **reversal)
        self.action("toggle")
        self.wait(lambda value: .08 < value.get("openness", 0) < .85, "No intermediate entry frame")
        entry = self.continuous_action("toggle")
        require(entry["after"]["closing"], "Entry toggle did not reverse toward closed")
        self.closed()
        self.record("toggle_during_entry", **entry)
        self.action("toggle")
        self.settled(4)
        self.action("accept")
        self.wait(lambda value: .15 < value.get("openness", 0) < .85, "No intermediate exit frame")
        exit_reversal = self.continuous_action("toggle")
        require(not exit_reversal["after"]["closing"], "Exit toggle did not reopen")
        self.settled(4)
        self.action("cancel")
        self.closed()
        self.record("toggle_during_exit", **exit_reversal)

    def reload_open(self):
        self.action("toggle")
        self.settled(4)
        self.action("jump", 6)
        before = self.settled(6)
        reply = self.control("reload").stdout
        after = self.settled(6)
        require(self.control("submap").stdout.strip() == "hyprflow", "Config reload lost modal submap")
        require(not self.control("configerrors").stdout.strip(), "Config reload introduced errors")
        require(self.query("activeworkspace")["id"] == 4, "Config reload changed actual workspace")
        self.action("cancel")
        self.closed()
        self.keyboard_restored()
        self.record("config_reload_while_open", before=before, after=after, reply=reply.strip())

    def unload_cycles(self):
        for index in range(10):
            active = index % 2 == 0
            self.focus_probe()
            if active:
                self.action("toggle")
                self.settled(4)
                self.action("jump", 7)
                self.settled(7)
            unloaded = self.control("plugin", "unload", str(self.artifact)).stdout
            require("hyprflow" not in self.control("plugin", "list").stdout.lower(), "Plugin remained registered after unload")
            require(self.query("activeworkspace")["id"] == 4, "Unload switched workspaces")
            require(self.control("submap").stdout.strip() == self.initial_submap, "Unload did not restore initial submap")
            self.keyboard_restored()
            loaded = self.control("plugin", "load", str(self.artifact)).stdout
            require(not self.status()["open"], "Reload restored stale flow state")
            require(not self.control("configerrors").stdout.strip(), "Plugin reload introduced config errors")
            mappings = self.mapped_artifact()
            self.record(f"unload_reload_{index + 1:02d}", active_at_unload=active, unload=unloaded.strip(),
                        load=loaded.strip(), focus_restored=True, submap_restored=True, mapped_artifact=mappings)

    def cleanup(self):
        if "hyprflow" not in self.control("plugin", "list").stdout.lower():
            self.control("plugin", "load", str(self.artifact))
        if self.status()["open"]:
            self.action("cancel")
            try:
                self.closed()
            except RuntimeError:
                # A hidden nested output can stop receiving parent frame callbacks.
                self.control("plugin", "unload", str(self.artifact))
                self.control("plugin", "load", str(self.artifact))
                self.evidence["cleanup_forced_unload"] = True
        self.control("dispatch", "hl.dsp.focus({ workspace = 4 })")
        if self.probe:
            self.control("dispatch", f'hl.dsp.window.close({{ window="address:{self.probe}" }})')
        if self.original_focus:
            self.control("dispatch", f'hl.dsp.focus({{ window="address:{self.original_focus}" }})')
        if self.process:
            self.process.wait(timeout=5)
        self.evidence["final_status"] = self.status()
        self.evidence["final_workspace"] = self.query("activeworkspace")["id"]
        self.evidence["final_submap"] = self.control("submap").stdout.strip()
        self.evidence["configerrors"] = self.control("configerrors").stdout.strip()
        require(self.evidence["final_workspace"] == 4 and not self.evidence["final_status"]["open"], "Cleanup did not restore closed origin 4")
        require(not self.evidence["configerrors"], "Final configuration has errors")
        self.evidence["runtime_alive"] = HELPER["session"](self.directory)["pid"] == self.state["pid"]
        self.evidence["final_artifact_sha256"] = digest(self.artifact)

    def run(self):
        try:
            self.start_probe()
            self.invalid_jump(False)
            self.invalid_jump(True)
            self.boundaries_and_empty()
            self.reversals()
            self.reload_open()
            self.unload_cycles()
            self.evidence["passed"] = True
        except Exception as error:
            self.evidence["error"] = str(error)
            raise
        finally:
            try:
                self.cleanup()
            except Exception as error:
                self.evidence["passed"] = False
                self.evidence["cleanup_error"] = str(error)
                raise
            finally:
                self.evidence["duration_seconds"] = round(time.monotonic() - self.started, 3)
                self.save()
        print(self.output / "manifest.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="Owned nested-session state directory")
    parser.add_argument("output", nargs="?", default=str(ROOT / "artifacts/lifecycle"))
    parser.add_argument("--artifact", default=str(ROOT / "build/hyprflow.so"))
    parser.add_argument("--sha256", required=True, help="Expected SHA-256 of the reviewed and loaded plugin")
    proof = LifecycleProof(parser.parse_args())
    try:
        with HELPER["isolated_input"](proof.state) as receipt:
            proof.evidence["input_isolation"] = receipt
            proof.run()
    except Exception as error:
        proof.evidence["passed"] = False
        proof.evidence.setdefault("error", str(error))
        raise
    finally:
        proof.save()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Verify workspace filtering in an owned, initially client-free nested session."""

import argparse
import json
from pathlib import Path
import runpy
import subprocess
import time

HELPER = runpy.run_path(str(Path(__file__).with_name("nested-session.py")))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class WorkspaceProof:
    def __init__(self, directory):
        self.directory = directory
        self.state = HELPER["session"](directory)
        self.processes = []
        self.positions = {}

    def ctl(self, *args, check=True):
        HELPER["session"](self.directory)
        return HELPER["control"](self.state, *args, check=check).stdout.strip()

    def status(self):
        return json.loads(self.ctl("repl", "return hl.plugin.hyprflow.status()"))

    def action(self, name, argument=None, check=True):
        arg = "" if argument is None else json.dumps(argument)
        return self.ctl("repl", f"return hl.plugin.hyprflow.{name}({arg})", check=check)

    def wait(self, predicate):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.03)
        raise RuntimeError(f"Timed out; flow status: {self.status()}")

    def settled(self, selected):
        time.sleep(.05)
        def ready():
            state = self.status()
            position = self.positions.get(selected, round(state.get("position", 0)))
            return (state.get("selected") == selected and state["openness"] > .99999
                    and not state["closing"] and abs(state["position"] - position) < .00001)
        self.wait(ready)

    def close(self, commit=False):
        if self.status()["open"]:
            self.action("accept" if commit else "cancel")
            self.wait(lambda: not self.status()["open"])

    def focus(self, workspace):
        self.ctl("dispatch", f"hl.dsp.focus({{workspace={json.dumps(workspace)}}})")

    def settings(self, include):
        self.close()
        if include:
            self.positions = {}
        self.ctl("eval", "hl.config({plugin={hyprflow={workspace_count=9,include_empty_workspaces="
                 + str(include).lower() + "}}})")
        require(not self.ctl("configerrors"), "Configuration rejected valid boolean")

    def fixture(self, workspace, name):
        self.focus(workspace)
        process = subprocess.Popen(
            ["kitty", "--config", "NONE", "--class", name, "-o", "confirm_os_window_close=0", "sleep", "300"],
            env=HELPER["environment"](self.state), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        self.processes.append(process)
        self.wait(lambda: any(c["class"] == name for c in json.loads(self.ctl("-j", "clients"))))

    def reject(self, workspace):
        result = self.action("jump", workspace, check=False)
        require("workspace is absent" in result, f"Empty workspace {workspace} was navigable: {result}")

    def run(self):
        require(not json.loads(self.ctl("-j", "clients")), "Use a fresh nested session without clients")
        raw = self.ctl("-j", "getoption", "plugin:hyprflow:include_empty_workspaces")
        require(raw.startswith("{"), f"Missing include_empty_workspaces option: {raw}")
        option = json.loads(raw)
        require(option.get("bool") is True, f"Expected default true: {option}")
        self.fixture(2, "hyprflow-filter-two")
        self.fixture(12, "hyprflow-filter-twelve")
        self.fixture("name:populated", "hyprflow-filter-named")
        named_id = json.loads(self.ctl("-j", "activeworkspace"))["id"]
        self.ctl("eval", 'hl.workspace_rule({workspace="name:empty",persistent=true})')
        self.focus("name:empty")
        empty_named_id = json.loads(self.ctl("-j", "activeworkspace"))["id"]
        self.focus(2)
        self.action("jump", 9)
        self.settled(9)
        self.action("jump", "name:empty")
        self.settled(empty_named_id)
        self.close()
        print("PASS default includes numeric placeholders and empty named workspaces", flush=True)

        self.positions = {named_id: 0, 2: 1, 12: 2}
        self.settings(False)
        self.action("toggle")
        self.settled(2)
        for empty in (1, 3, 7, 9, "name:empty"):
            self.reject(empty)
        for target in ("name:populated", 12, 2):
            self.action("jump", target)
            self.settled(named_id if isinstance(target, str) else target)
        self.action("left")
        self.settled(named_id)
        self.action("left")
        self.settled(named_id)
        self.action("right")
        self.settled(2)
        self.action("right")
        self.settled(12)
        self.action("right")
        self.settled(12)
        self.close()
        require(json.loads(self.ctl("-j", "activeworkspace"))["id"] == 2, "Cancel changed workspace")
        print("PASS filter excludes empty persistent/named/placeholders; navigation skips gaps and clamps", flush=True)

        self.focus(1)
        self.action("toggle")
        self.settled(2)
        require(self.status()["origin"] == 1, "Lost empty origin")
        self.reject(1)
        self.close()
        require(json.loads(self.ctl("-j", "activeworkspace"))["id"] == 1, "Cancel lost empty origin")
        self.action("toggle")
        self.settled(2)
        self.close(True)
        require(json.loads(self.ctl("-j", "activeworkspace"))["id"] == 2, "Accept failed from empty origin")
        self.focus(20)
        self.action("toggle")
        self.settled(12)
        self.close()
        require(json.loads(self.ctl("-j", "activeworkspace"))["id"] == 20, "Cancel lost high empty origin")
        print("PASS empty origin excluded; next/last populated selection, cancel and accept", flush=True)

        # Membership is snapshotted at opening, then refreshed on the next open.
        for client in json.loads(self.ctl("-j", "clients")):
            self.ctl("dispatch", f'hl.dsp.window.close({{window="address:{client["address"]}"}})')
        self.wait(lambda: not json.loads(self.ctl("-j", "clients")))
        result = self.action("toggle", check=False)
        require("no nonempty workspaces" in result and not self.status()["open"], "All-empty flow did not stay closed")
        require(self.ctl("submap") == "default", "All-empty opening changed input submap")
        self.settings(True)
        self.action("jump", 9)
        self.settled(9)
        self.close()
        self.ctl("reload")
        require(not self.ctl("configerrors"), "Reload has config errors")
        raw = self.ctl("-j", "getoption", "plugin:hyprflow:include_empty_workspaces")
        require(raw.startswith("{"), f"Missing include_empty_workspaces option: {raw}")
        option = json.loads(raw)
        require(option.get("bool") is True, "Reload failed to restore default true")
        print("PASS all-empty stays closed; re-enable and reload restore placeholders", flush=True)

    def cleanup(self):
        self.close()
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
        self.ctl("reload")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="Owned directory from nested-session.py start")
    args = parser.parse_args()
    proof = WorkspaceProof(args.directory)
    try:
        with HELPER["isolated_input"](proof.state):
            proof.run()
    finally:
        proof.cleanup()


if __name__ == "__main__":
    main()

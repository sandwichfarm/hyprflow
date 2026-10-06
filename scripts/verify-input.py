#!/usr/bin/env python3
"""Verify modal keyboard isolation and focus restoration against a real raw-input client."""

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import runpy
import subprocess
import time

HERE = Path(__file__).resolve().parent
HELPER = runpy.run_path(str(HERE / "nested-session.py"))
KEYBOARD = runpy.run_path(str(HERE / "nested-key.py"))
PROOF = runpy.run_path(str(HERE / "capture-proof.py"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("output")
    args = parser.parse_args()
    state = HELPER["session"](args.directory)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    log = output / "received.bin"
    log.write_bytes(b"")
    ready = log.with_suffix(".ready")
    ready.unlink(missing_ok=True)
    control = HELPER["control"]
    send_key = lambda key: KEYBOARD["send_key"](args.directory, key)
    evidence = {"pid": state["pid"], "checks": []}
    isolation = ExitStack()
    address = None
    try:
        evidence["input_isolation"] = isolation.enter_context(HELPER["isolated_input"](state))
        assert not PROOF["status"](state)["open"], "Input proof must start with flow closed"
        control(state, "dispatch", "hl.dsp.focus({ workspace = 4 })")
        subprocess.Popen(
            ["kitty", "--config", "NONE", "--class", "hyprflow-input-probe", "-o", "confirm_os_window_close=0",
             "python3", str(HERE / "input-fixture.py"), str(log)],
            env=HELPER["environment"](state), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(50):
            clients = json.loads(control(state, "-j", "clients").stdout)
            probe = next((item for item in clients if item["class"] == "hyprflow-input-probe"), None)
            if probe:
                address = probe["address"]
                break
            time.sleep(0.1)
        assert address, "Input probe did not map"
        control(state, "dispatch", f'hl.dsp.focus({{ window="address:{address}" }})')
        for _ in range(50):
            if ready.exists():
                break
            time.sleep(0.1)
        assert ready.exists(), "Input probe did not enter raw mode"
        send_key("Z")
        time.sleep(0.15)
        assert log.read_bytes() == b"z", f"Baseline input did not arrive: {log.read_bytes()!r}"
        evidence["checks"].append({"baseline": "z"})
        for exit_key in ("Return", "Escape"):
            send_key("F10")
            PROOF["wait_settled"](state, 4, time.monotonic())
            log.write_bytes(b"")
            send_key("Z")
            time.sleep(0.1)
            assert log.read_bytes() == b"", f"Unbound Z leaked through open flow: {log.read_bytes()!r}"
            send_key(exit_key)
            actual, _ = PROOF["wait_settled"](state, None, time.monotonic())
            assert not actual["open"], f"{exit_key} did not close flow"
            assert log.read_bytes() == b"", f"{exit_key} leaked into client: {log.read_bytes()!r}"
            send_key("Z")
            time.sleep(0.15)
            assert log.read_bytes() == b"z", f"Focus did not return after {exit_key}: {log.read_bytes()!r}"
            evidence["checks"].append({"exit_key": exit_key, "unbound_blocked": True,
                                        "exit_key_blocked": True, "focus_restored": True})
        evidence["passed"] = True
    finally:
        try:
            if address:
                control(state, "dispatch", f'hl.dsp.window.close({{ window="address:{address}" }})')
        finally:
            try:
                isolation.close()
            finally:
                (output / "input-manifest.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(output / "input-manifest.json")


if __name__ == "__main__":
    main()

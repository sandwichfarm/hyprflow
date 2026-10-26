#!/usr/bin/env python3
"""Prove an incompatible plugin is rejected while the owned compositor remains usable."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import time

HELPER = runpy.run_path(str(Path(__file__).with_name("nested-session.py")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--reason", default="headers do not match the running Hyprland ABI")
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    state = HELPER["session"](args.directory)
    artifact = args.artifact.resolve(strict=True)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert digest == args.sha256, "Artifact hash differs"
    retries = []

    def control(*args):
        result = HELPER["control"](state, *args, check=False)
        # A failed load schedules config reload. Retry only reads, never a mutation.
        if args[0] in ("plugin", "-j", "configerrors") and args[:2] != ("plugin", "load") and args[:2] != ("plugin", "unload"):
            for attempt in range(3):
                if result.returncode != 6:
                    break
                HELPER["session"](args_directory)
                retries.append({"command": list(args), "attempt": attempt + 1})
                time.sleep(.1)
                result = HELPER["control"](state, *args, check=False)
        return result

    args_directory = args.directory
    before = control("plugin", "list").stdout
    assert "hyprflow" not in before, "Start without Hyprflow loaded"
    replies = []
    try:
        for _ in range(3):
            response = control("plugin", "load", str(artifact))
            # Hyprland can return exit0 for a failed plugin load. Inspect the registry and reason.
            assert args.reason in response.stdout, f"Missing expected rejection: {response.stdout}"
            registry = control("plugin", "list")
            assert registry.returncode == 0 and registry.stdout.strip() == before.strip(), (
                f"Rejected plugin registry before={before!r}, after={registry.stdout!r}, "
                f"exit={registry.returncode}, stderr={registry.stderr!r}")
            assert json.loads(control("-j", "monitors").stdout), "Compositor lost its outputs"
            assert HELPER["session"](args.directory)["start_time"] == state["start_time"], "Compositor restarted"
            replies.append({"exit_code": response.returncode, "reason": args.reason})
        assert not control("configerrors").stdout.strip()
    finally:
        if "hyprflow" in control("plugin", "list").stdout:
            control("plugin", "unload", str(artifact))
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == digest
    print(json.dumps({"passed": True, "artifact_sha256": digest, "attempts": replies, "runtime_survived": True, "read_retries": retries}, indent=2))


if __name__ == "__main__":
    main()

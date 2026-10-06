#!/usr/bin/env python3
"""Start and control one isolated Hyprland compositor without touching the host session."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import runpy
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def start_time(pid):
    """Identify the process lifetime, protecting stop against PID reuse."""
    return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]


def session(path):
    state = json.loads((Path(path) / "session.json").read_text())
    if start_time(state["pid"]) != state["start_time"]:
        raise RuntimeError("Owned compositor has exited; PID belongs to another process")
    return state


def environment(state):
    env = os.environ.copy()
    env.update(state["env"])
    return env


def control(state, *args, check=True):
    return subprocess.run(
        ["hyprctl", "-i", state["signature"], *args], env=environment(state),
        text=True, capture_output=True, check=check, timeout=10,
    )


@contextmanager
def isolated_input(state):
    """Exclude parent Wayland modifier state only while an automated nested proof runs."""
    keyboards = json.loads(control(state, "-j", "devices").stdout)["keyboards"]
    present = any(item["name"] == "wl_keyboard" for item in keyboards)
    receipt = {"device": "wl_keyboard", "nested_only": True, "present": present,
               "disabled_during_proof": False, "restored": False}
    config = Path(state["directory"]) / "nested.lua"
    original = config.read_bytes()
    backup = config.with_name(f"nested-input-backup-{time.time_ns()}.lua")
    try:
        if present:
            # Keep isolation in force through the reload/unload lifecycle proof.
            shutil.copy2(config, backup)
            config.write_bytes(original + b'\n-- Temporary automated input isolation.\n'
                               b'hl.device({ name="wl_keyboard", enabled=false })\n')
            control(state, "eval", 'hl.device({ name="wl_keyboard", enabled=false })')
            receipt["disabled_during_proof"] = True
        yield receipt
    finally:
        if present:
            config.write_bytes(original)
            control(state, "eval", 'hl.device({ name="wl_keyboard", enabled=true })')
            receipt["restored"] = True
            backup.unlink(missing_ok=True)


def start():
    parent_runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    parent_display = os.environ.get("WAYLAND_DISPLAY", "wayland-1")
    parent_socket = Path(parent_runtime) / parent_display
    if not parent_socket.is_socket():
        raise RuntimeError(f"Parent Wayland socket missing: {parent_socket}")
    # Linux UNIX socket paths must stay below 108 bytes, including Hyprland's signature.
    folder = Path(tempfile.mkdtemp(prefix="hf-"))
    for name in ("r", "config", "cache", "state"):
        (folder / name).mkdir(mode=0o700)
    shutil.copy2(ROOT / "config/nested.lua", folder / "nested.lua")
    isolated = {
        "XDG_RUNTIME_DIR": str(folder / "r"),
        "XDG_CONFIG_HOME": str(folder / "config"),
        "XDG_CACHE_HOME": str(folder / "cache"),
        "XDG_STATE_HOME": str(folder / "state"),
        "WAYLAND_DISPLAY": str(parent_socket),
        "AQ_BACKEND": "wayland",
        "HYPRLAND_INSTANCE_SIGNATURE": "",
        "HYPRLAND_NO_SD_VARS": "1",
        "HYPRLAND_NO_SD_NOTIFY": "1",
    }
    env = os.environ.copy()
    env.update(isolated)
    with (folder / "compositor.log").open("w") as log:
        process = subprocess.Popen(
            ["/usr/bin/Hyprland", "--config", str(folder / "nested.lua")],
            env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
        )
    state = {"directory": str(folder), "pid": process.pid, "start_time": start_time(process.pid), "env": isolated}
    for _ in range(150):
        if process.poll() is not None:
            raise RuntimeError(f"Nested compositor exited ({process.returncode}); inspect {folder}/compositor.log")
        sockets = list((folder / "r/hypr").glob("*/.socket.sock"))
        if sockets:
            state["signature"] = sockets[0].parent.name
            state["env"]["HYPRLAND_INSTANCE_SIGNATURE"] = state["signature"]
            displays = [path for path in (folder / "r").glob("wayland-*") if path.is_socket()]
            if not displays:
                time.sleep(0.1)
                continue
            state["env"]["WAYLAND_DISPLAY"] = displays[0].name
            if control(state, "-j", "monitors", check=False).returncode == 0:
                (folder / "session.json").write_text(json.dumps(state, indent=2) + "\n")
                print(json.dumps(state, indent=2))
                return
        time.sleep(0.1)
    process.terminate()
    raise RuntimeError(f"Nested compositor startup timed out; inspect {folder}/compositor.log")


def fixtures(state, calibration=False):
    if not shutil.which("kitty"):
        raise RuntimeError("Fixture launcher requires existing kitty installation")
    clients = json.loads(control(state, "-j", "clients").stdout)
    for client in clients:
        if client["class"] in {f"hyprflow-fixture-{index}" for index in range(1, 8)}:
            control(state, "dispatch", f'hl.dsp.window.close({{ window="address:{client["address"]}" }})')
    colors = runpy.run_path(str(ROOT / "scripts/workspace-fixture.py"))["CALIBRATION_COLORS"]
    for index in range(1, 8):
        command = ["kitty", "--config", "NONE", "--class", f"hyprflow-fixture-{index}", "--title", f"Hyprflow Workspace {index}",
                   "-o", "confirm_os_window_close=0", "-o", "font_size=14", "-o", "cursor_blink_interval=0",
                   "-o", "background=#0b1020", "python3", str(ROOT / "scripts/workspace-fixture.py"), str(index)]
        if calibration:
            command[command.index("background=#0b1020")] = "background=#" + colors[index - 1]
            command.append("--calibration")
        control(state, "dispatch", f'hl.dsp.focus({{ workspace = {index} }})')
        subprocess.Popen(command, env=environment(state), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(50):
            clients = json.loads(control(state, "-j", "clients").stdout)
            if any(client["class"] == f"hyprflow-fixture-{index}" for client in clients):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError(f"Workspace {index} fixture did not map")
        time.sleep(0.3)
    control(state, "dispatch", 'hl.dsp.focus({ workspace = 4 })')
    print(control(state, "-j", "clients").stdout)


def host_control(signature, *args):
    """Host IPC is reserved for placing/restoring this compositor's exact window."""
    return subprocess.run(["hyprctl", "-i", signature, *args], text=True, capture_output=True, check=True, timeout=10)


def place(state):
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    if not signature or signature == state["signature"]:
        raise RuntimeError("Run place from the parent desktop session")
    clients = json.loads(host_control(signature, "-j", "clients").stdout)
    client = next((item for item in clients if item["pid"] == state["pid"] and item["class"] == "aquamarine"), None)
    if not client:
        raise RuntimeError("Exact owned nested compositor window not found in parent")
    workspace = json.loads(host_control(signature, "-j", "activeworkspace").stdout)
    snapshot = Path(state["directory"]) / "host-window-before.json"
    if not snapshot.exists():
        snapshot.write_text(json.dumps({"signature": signature, "client": client, "workspace": workspace}, indent=2))
    selector = f'window="address:{client["address"]}"'
    # Exact Hyprland 0.56.2 uses on/off here; unsupported set/unset silently toggle.
    operations = [f'hl.dsp.window.float({{ {selector}, action="on" }})',
                  f'hl.dsp.window.move({{ {selector}, workspace={workspace["id"]}, silent=true }})',
                  f'hl.dsp.window.resize({{ {selector}, x=1280, y=720, relative=false }})',
                  f'hl.dsp.window.move({{ {selector}, x=320, y=160, relative=false }})',
                  f'hl.dsp.window.pin({{ {selector}, action="on" }})']
    for expression in operations:
        print(host_control(signature, "dispatch", expression).stdout, end="")


def restore(state):
    snapshot = Path(state["directory"]) / "host-window-before.json"
    if not snapshot.exists():
        return
    saved = json.loads(snapshot.read_text())
    client, signature = saved["client"], saved["signature"]
    clients = json.loads(host_control(signature, "-j", "clients").stdout)
    if not any(item["address"] == client["address"] and item["pid"] == state["pid"] for item in clients):
        raise RuntimeError("Refusing to restore host placement: owned window identity changed")
    selector = f'window="address:{client["address"]}"'
    pinned = "on" if client["pinned"] else "off"
    operations = [f'hl.dsp.window.pin({{ {selector}, action="{pinned}" }})',
                  f'hl.dsp.window.move({{ {selector}, workspace={client["workspace"]["id"]}, silent=true }})',
                  f'hl.dsp.window.resize({{ {selector}, x={client["size"][0]}, y={client["size"][1]}, relative=false }})',
                  f'hl.dsp.window.move({{ {selector}, x={client["at"][0]}, y={client["at"][1]}, relative=false }})']
    if not client["floating"]:
        operations.append(f'hl.dsp.window.float({{ {selector}, action="off" }})')
    for expression in operations:
        host_control(signature, "dispatch", expression)


def stop(state):
    restore(state)
    control(state, "dispatch", "hl.dsp.exit()", check=False)
    for _ in range(50):
        try:
            stat = Path(f'/proc/{state["pid"]}/stat').read_text().rsplit(")", 1)[1].split()
        except FileNotFoundError:
            print(f"Owned nested compositor PID {state['pid']} stopped")
            return
        if stat[0] == "Z":
            print(f"Owned nested compositor PID {state['pid']} stopped")
            return
        time.sleep(0.1)
    if start_time(state["pid"]) == state["start_time"]:
        os.kill(state["pid"], signal.SIGTERM)
    raise RuntimeError("Graceful exit timed out; SIGTERM sent only to the verified owned compositor")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "status", "ctl", "fixtures", "capture", "place", "stop", "env"))
    parser.add_argument("directory", nargs="?", help="Directory printed by start")
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "start":
        start()
        return
    if not args.directory:
        parser.error("directory is required for an existing session")
    state = session(args.directory)
    if args.action == "status":
        print(json.dumps(state, indent=2))
        print(control(state, "-j", "monitors").stdout)
        print(control(state, "configerrors").stdout)
    elif args.action == "ctl":
        result = control(state, *args.args, check=False)
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        sys.exit(result.returncode)
    elif args.action == "fixtures":
        fixtures(state, "--calibration" in args.args)
    elif args.action == "capture":
        if not args.args:
            parser.error("capture requires an output PNG path")
        subprocess.run(["grim", *args.args], env=environment(state), check=True, timeout=10)
    elif args.action == "env":
        print(json.dumps(state["env"], indent=2))
    elif args.action == "place":
        place(state)
    elif args.action == "stop":
        stop(state)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(str(error))

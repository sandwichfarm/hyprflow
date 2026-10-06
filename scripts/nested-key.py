#!/usr/bin/env python3
"""Send a virtual keyboard event only to a validated nested compositor socket."""

import argparse
import array
import ctypes
import os
from pathlib import Path
import runpy
import socket
import struct
import time

KEYS = {"F10": 68, "Left": 105, "Right": 106, "Return": 28, "Escape": 1, "Z": 44,
        **{str(index): index + 1 for index in range(1, 8)}}


def word(value):
    return struct.pack("=I", value)


def string(value):
    data = value.encode() + b"\0"
    return word(len(data)) + data + b"\0" * (-len(data) % 4)


def send(connection, object_id, opcode, payload=b"", fd=None):
    message = word(object_id) + word((len(payload) + 8) << 16 | opcode) + payload
    ancillary = [] if fd is None else [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))]
    connection.sendmsg([message], ancillary)


def roundtrip(connection, callback_id):
    """Wait until compositor has processed preceding requests before sending input."""
    send(connection, 1, 0, word(callback_id))
    pending = b""
    while True:
        pending += connection.recv(65536)
        while len(pending) >= 8:
            object_id, header = struct.unpack_from("=II", pending)
            size, opcode = header >> 16, header & 65535
            if len(pending) < size:
                break
            payload, pending = pending[8:size], pending[size:]
            if object_id == 1 and opcode == 0:
                raise RuntimeError(f"Wayland server rejected input protocol: {payload!r}")
            if object_id == callback_id:
                return


def keymap():
    """Use installed xkbcommon to create the same default US keymap as the fixture session."""
    library = ctypes.CDLL("libxkbcommon.so.0")
    library.xkb_context_new.restype = ctypes.c_void_p
    library.xkb_keymap_new_from_names.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    library.xkb_keymap_new_from_names.restype = ctypes.c_void_p
    library.xkb_keymap_get_as_string.argtypes = [ctypes.c_void_p, ctypes.c_int]
    library.xkb_keymap_get_as_string.restype = ctypes.c_void_p
    context = library.xkb_context_new(0)
    mapping = library.xkb_keymap_new_from_names(context, None, 0)
    if not context or not mapping:
        raise RuntimeError("Could not create virtual keyboard keymap")
    data = ctypes.string_at(library.xkb_keymap_get_as_string(mapping, 1)) + b"\0"
    fd = os.memfd_create("hyprflow-keymap")
    os.write(fd, data)
    return fd, len(data)


def send_key(directory, key):
    helper = runpy.run_path(str(Path(__file__).with_name("nested-session.py")))
    state = helper["session"](directory)
    path = Path(state["env"]["XDG_RUNTIME_DIR"]) / state["env"]["WAYLAND_DISPLAY"]
    connection = socket.socket(socket.AF_UNIX)
    connection.settimeout(3)
    connection.connect(str(path))
    send(connection, 1, 1, word(2))  # wl_display.get_registry
    send(connection, 1, 0, word(3))  # wl_display.sync
    globals_found = {}
    pending = b""
    complete = False
    while not complete:
        pending += connection.recv(65536)
        while len(pending) >= 8:
            object_id, header = struct.unpack_from("=II", pending)
            size, opcode = header >> 16, header & 65535
            if len(pending) < size:
                break
            payload, pending = pending[8:size], pending[size:]
            if object_id == 3:
                complete = True
            elif object_id == 2 and opcode == 0:
                name, length = struct.unpack_from("=II", payload)
                interface = payload[8:8 + length - 1].decode()
                version = struct.unpack_from("=I", payload, 8 + ((length + 3) & ~3))[0]
                globals_found[interface] = (name, version)
    for interface, object_id in (("wl_seat", 4), ("zwp_virtual_keyboard_manager_v1", 5)):
        if interface not in globals_found:
            raise RuntimeError(f"Nested compositor does not expose {interface}")
        name, _ = globals_found[interface]
        send(connection, 2, 0, word(name) + string(interface) + word(1) + word(object_id))
    send(connection, 5, 0, word(4) + word(6))
    fd, length = keymap()
    send(connection, 6, 0, word(1) + word(length), fd)
    os.close(fd)
    send(connection, 6, 2, word(0) * 4)
    roundtrip(connection, 7)
    for pressed in (1, 0):
        send(connection, 6, 1, word(int(time.monotonic() * 1000) & 0xFFFFFFFF) + word(KEYS[key]) + word(pressed))
        roundtrip(connection, 9 - pressed)
        time.sleep(0.035)
    connection.close()
    print(f"Sent {key} to nested PID {state['pid']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("key", choices=KEYS)
    args = parser.parse_args()
    send_key(args.directory, args.key)

#!/usr/bin/env python3
"""Raw terminal input probe: every received byte is appended to an explicit log."""

import os
from pathlib import Path
import sys
import termios
import tty


def main():
    destination = Path(sys.argv[1])
    original = termios.tcgetattr(sys.stdin)
    tty.setraw(sys.stdin.fileno())
    destination.with_suffix(".ready").write_text("ready\n")
    print("HYPRFLOW INPUT PROBE\r\nEvery delivered byte is recorded.\r", flush=True)
    try:
        while True:
            data = os.read(sys.stdin.fileno(), 1024)
            if not data:
                break
            with destination.open("ab") as output:
                output.write(data)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original)


if __name__ == "__main__":
    main()

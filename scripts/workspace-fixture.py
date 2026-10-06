#!/usr/bin/env python3
"""Render deterministic, distinct terminal clients for nested compositor proofs."""

import math
import shutil
import signal
import sys
import time

SCENES = [
    ("TERMINAL", "BUILD / HYPERLAND", (64, 205, 169), "hyprflow  /  build successful", "C++23  ·  EGL  ·  OpenGL ES"),
    ("STUDIO", "SPECTRAL / STUDIES", (236, 160, 109), "A study in color and motion", "EXHIBITION 024     AUTUMN 2026"),
    ("CODE", "WORKSPACE / ENGINE", (126, 154, 246), "projection.cpp", "Perspective     reflection     continuity"),
    ("MUSIC", "MIDNIGHT / SIGNAL", (189, 132, 228), "Midnight Signal", "SYNTHETIC WAVES           04:32 / 06:18"),
    ("METRICS", "SYSTEM / OBSERVER", (91, 185, 222), "Frame timing", "RENDER  1.62 ms         REFRESH  60 Hz"),
    ("NOTES", "IDEAS / IN MOTION", (221, 197, 124), "Small details, continuous motion.", "Design journal          No. 006"),
    ("NETWORK", "RELAY / CONSTELLATION", (224, 122, 157), "Connected systems", "7 nodes        42 connections        healthy"),
]
CALIBRATION_COLORS = ["2476d7", "e58338", "2fb08e", "edeee8", "d2486f", "8b53c5", "47a6de"]


def color(rgb):
    return f"\033[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def draw_calibration(index):
    columns, lines = shutil.get_terminal_size((80, 40))
    rgb = tuple(int(CALIBRATION_COLORS[index - 1][offset:offset + 2], 16) for offset in (0, 2, 4))
    background = f"\033[48;2;{rgb[0]};{rgb[1]};{rgb[2]}m"
    title = f"WORKSPACE {index}"
    output = (background + "\033[38;2;20;25;35m\033[?25l\033[2J\033[H"
              + f"\033[2;3H{index}  TOP LEFT\033[2;{max(3, columns - 12)}HTOP RIGHT  {index}"
              + f"\033[{lines // 2};{max(1, (columns - len(title)) // 2)}H\033[1m{title}\033[22m"
              + f"\033[{lines - 1};3H{index}  BOTTOM LEFT\033[{lines - 1};{max(3, columns - 15)}HBOTTOM RIGHT  {index}")
    sys.stdout.write(output)
    sys.stdout.flush()


def draw(index, calibration=False):
    if calibration:
        draw_calibration(index)
        return
    columns, lines = shutil.get_terminal_size((100, 40))
    label, subtitle, tint, title, footer = SCENES[index - 1]
    width = min(columns - 8, 100)
    art_rows = max(8, lines - 16)
    output = ["\033[?25l\033[2J\033[H", "", color(tint) + f"    {index:02d}  /  {label}".ljust(width),
              "\033[38;2;115;125;149m    " + "─" * width, "", "    " + subtitle, ""]
    for row in range(art_rows):
        line = "    "
        for column in range(width):
            x = column / width * 2 - 1
            y = row / art_rows * 2 - 1
            radius = math.hypot(x, y * 0.65)
            phase = math.sin(x * (8 + index) + y * 4 + index)
            value = max(0.1, min(1, (1 - radius) * 0.9 + phase * 0.23))
            rgb = tuple(int(channel * value) for channel in tint)
            char = " ░▒▓█"[min(4, int(value * 5))]
            line += color(rgb) + char
        output.append(line)
    output += ["", "\033[1m" + color(tint) + "    " + title + "\033[22m", "",
               "\033[38;2;150;159;180m    " + footer, "", "    " + "─" * width,
               "\033[38;2;90;100;124m    HYPRFLOW     WORKSPACE " + str(index) + "                    NESTED SESSION\033[0m"]
    sys.stdout.write("\n".join(output))
    sys.stdout.flush()


def main():
    index = int(sys.argv[1])
    if not 1 <= index <= len(SCENES):
        raise SystemExit("Fixture index must be 1 through 7")
    calibration = "--calibration" in sys.argv[2:]
    signal.signal(signal.SIGWINCH, lambda *_: draw(index, calibration))
    draw(index, calibration)
    try:
        while True:
            time.sleep(60)
    finally:
        sys.stdout.write("\033[?25h\033[0m")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Verify native workspace proportions and appearance controls; record three configurations.

Requires an owned nested session and its exact loaded artifact. Run with seven
calibration fixtures; the video/blur phase replaces them with detailed fixtures.
"""
import argparse
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import runpy
import subprocess
import time

from PIL import ImageChops, ImageStat, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
BASE = runpy.run_path(str(ROOT / "scripts/verify-configuration.py"))
HELPER = BASE["HELPER"]
require = BASE["require"]
CAPTURE = runpy.run_path(str(ROOT / "scripts/capture-proof.py"))

DEFAULTS = {**BASE["DEFAULTS"], "workspace_overlay": 0, "background_color": "rgb(000000)",
            "background_opacity": 1, "background_blur": 0, "reflection_opacity": .34,
            "show_labels": 1, "center_y": .4}


class AppearanceProof(BASE["ConfigurationProof"]):
    def settled(self, selected):
        # Software rendering in a virtual GPU can take longer than desktop hardware.
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            actual = self.status()
            if selected is None and not actual["open"]:
                return actual
            if (selected is not None and actual.get("selected") == selected and not actual.get("closing", True)
                    and actual.get("openness", 0) >= .999999 and abs(actual["position"] - (selected - 1)) < .00001):
                time.sleep(.3)
                return actual
            time.sleep(.1)
        raise RuntimeError(f"Selection {selected} did not settle: {actual}")

    def candidate(self):
        for key in DEFAULTS:
            require(self.control("getoption", "plugin:hyprflow:" + key) != "no such option", f"Missing option: {key}")
        self.record("all_appearance_options_registered")
        self.default_frames()
        self.open_four()
        frame = self.frame("aspect-native")
        bounds = self.bright_bounds(frame)
        aspect = (bounds[2] - bounds[0]) / (bounds[3] - bounds[1])
        require(abs(aspect - frame.width / frame.height) < .015, "Selected workspace has matte padding or incorrect aspect")
        # Full source corners, top/bottom labels, and centered title also remain visible.
        self.record("native_workspace_aspect", bounds=bounds, measured=aspect, expected=frame.width / frame.height)
        self.geometry()
        self.borders()
        self.backgrounds()
        self.invalid_effects()
        self.invalid_reload_closed()
        self.sample_configuration()
        self.lifecycle()
        self.detailed_and_video()

    def lifecycle(self):
        # Exercise blur resources and new appearance values through the same
        # reload and unload checks as the existing size/border configuration.
        config = Path(self.state["directory"]) / "nested.lua"
        original = config.read_bytes()
        values = {"workspace_overlay": 1, "background_opacity": .3,
                  "background_color": "rgb(182030)", "background_blur": 16,
                  "reflection_opacity": .2, "show_labels": 0, "center_y": .5}
        try:
            config.write_bytes(original + ("\nhl.config(" + BASE["lua"]({"plugin": {"hyprflow": values}}) + ")\n").encode())
            super().lifecycle()
            self.record("appearance_and_blur_survive_reload", settings=values)
        finally:
            config.write_bytes(original)
            self.control("reload")

    def backgrounds(self):
        self.settings(**DEFAULTS)
        self.open_four()
        native = self.frame("solid-stage")
        require(max(native.getpixel((20, 100))) == 0, "Default stage is not black")
        self.settings(workspace_overlay=1, background_opacity=0)
        overlay = self.frame("desktop-overlay")
        original = self.output / "default-closed.png"
        from PIL import Image
        desktop = Image.open(original).convert("RGB")
        crop = (0, 80, overlay.width, 130)
        require(ImageChops.difference(overlay.crop(crop), desktop.crop(crop)).getbbox() is None,
                "Clear overlay did not preserve the original workspace pixels")
        self.action("jump", 7)
        self.settled(7)
        selected = self.frame("overlay-selection-seven")
        require(ImageChops.difference(selected.crop(crop), desktop.crop(crop)).getbbox() is None,
                "Backdrop changed to the selected destination before acceptance")
        self.action("jump", 4)
        self.settled(4)
        for opacity in (.25, .75, 1):
            self.settings(background_opacity=opacity)
            tinted = self.frame(f"opacity-{opacity}")
            source = desktop.getpixel((20, 100))
            actual = tinted.getpixel((20, 100))
            require(max(abs(a - round(b * (1 - opacity))) for a, b in zip(actual, source)) <= 2,
                    f"Background opacity is incorrect: {actual}")
            self.record("background_opacity", opacity=opacity, pixel=actual)
        self.settings(background_color="rgba(ff000080)", background_opacity=1)
        red = self.frame("background-color-alpha")
        sample = red.getpixel((20, 100)); source = desktop.getpixel((20, 100))
        expected = (round(128 + source[0] * 127 / 255), round(source[1] * 127 / 255), round(source[2] * 127 / 255))
        require(max(abs(a - b) for a, b in zip(sample, expected)) < 3, "Tint color alpha was not multiplied into opacity")
        self.settings(workspace_overlay=0)
        solid = self.frame("solid-color-alpha")
        require(max(abs(a - b) for a, b in zip(solid.getpixel((20, 100)), (128, 0, 0))) <= 1,
                "Solid background tint did not blend over black")
        self.record("desktop_overlay_origin_and_tint_alpha")
        self.settings(**DEFAULTS)
        with_effects = self.frame("reflections-labels-on")
        self.settings(reflection_opacity=0, show_labels=0)
        without_effects = self.frame("reflections-labels-off")
        bounds = self.bright_bounds(without_effects)
        below = (int(with_effects.width * .35), bounds[3] + 2, int(with_effects.width * .65), with_effects.height)
        require(ImageStat.Stat(without_effects.crop(below)).sum == [0, 0, 0], "Disabled reflections/captions remained visible")
        require(ImageChops.difference(with_effects.crop(below), without_effects.crop(below)).getbbox() is not None,
                "Reflection and caption controls did not change pixels")
        self.settings(show_labels=1)
        labels = self.frame("labels-only")
        require(ImageChops.difference(labels.crop(below), without_effects.crop(below)).getbbox() is not None,
                "Caption toggle did not restore labels")
        self.settings(show_labels=0, reflection_opacity=.7)
        reflections = self.frame("reflections-strong")
        require(ImageStat.Stat(reflections.crop(below)).sum[0] > ImageStat.Stat(with_effects.crop(below)).sum[0],
                "Reflection opacity did not increase reflection brightness")
        self.settings(reflection_opacity=0, center_y=.5)
        centered = self.bright_bounds(self.frame("center-half"))
        require(abs((centered[1] + centered[3]) / 2 - with_effects.height * .5) < 1, "Configured vertical center was not applied")
        self.record("reflections_labels_and_vertical_center")
        self.settings(**DEFAULTS)

    def invalid_effects(self):
        # Check the same application boundary used by the live renderer, including NaN.
        self.settings(workspace_overlay=1, background_opacity=.35, background_blur=0,
                      reflection_opacity=.2, center_y=.4, show_labels=1, background_color="rgb(182030)")
        good = self.frame("effects-last-valid")
        cases = {"background_opacity": [-.1, 1.1, "0/0"], "background_blur": [-1, 65, "math.huge"],
                 "reflection_opacity": [-.1, 1.1], "center_y": [-.1, 1.1],
                 "workspace_overlay": [-1, 2], "show_labels": [-1, 2], "background_color": ["bad", "rgb(ff0000) rgb(0000ff)"]}
        for key, values in cases.items():
            for value in values:
                expression = value if value in ("0/0", "math.huge") else json.dumps(value)
                self.control("repl", f"return hl.config({{plugin={{hyprflow={{{key}={expression}}}}}}})", check=False)
                time.sleep(.4)
                self.control("dismissnotify", "-1")
                actual = self.frame("rejected-" + key + "-" + str(values.index(value)))
                require(ImageChops.difference(good, actual).getbbox() is None, f"Invalid {key} replaced the last valid appearance")
        self.record("invalid_effects_retain_last_valid_pixels", cases=sum(map(len, cases.values())))
        self.settings(**DEFAULTS)

    def detailed_and_video(self):
        self.reset()
        with redirect_stdout(StringIO()):
            HELPER["fixtures"](self.state, calibration=False)
        self.prime_fixtures()
        self.settings(**DEFAULTS)
        self.open_four()
        self.settings(workspace_overlay=1, background_opacity=0, background_blur=0)
        sharp = self.frame("blur-zero")
        self.settings(background_blur=16)
        time.sleep(1)
        blurred = self.frame("blur-sixteen")
        crop = (40, 30, sharp.width - 40, 130)
        def energy(image):
            region = image.crop(crop).convert("L").filter(ImageFilter.FIND_EDGES)
            return ImageStat.Stat(region.crop((2, 2, region.width - 2, region.height - 2))).mean[0]
        sharp_energy, blurred_energy = energy(sharp), energy(blurred)
        require(blurred_energy < sharp_energy * .65, f"Background blur did not smooth desktop detail: edge energy {sharp_energy:.3f} -> {blurred_energy:.3f}")
        # Centered card stays sharp while only the surrounding desktop is blurred.
        size = min(.58 * sharp.height, .38 * sharp.width)
        card_height = size * sharp.height / sharp.width
        center_crop = (round(sharp.width / 2 - size / 2 + 3), round(sharp.height * .4 - card_height / 2 + 3),
                       round(sharp.width / 2 + size / 2 - 3), round(sharp.height * .4 + card_height / 2 - 3))
        require(ImageChops.difference(sharp.crop(center_crop), blurred.crop(center_crop)).getbbox() is None,
                "Background blur also blurred the workspace card")
        self.record("background_blur_preserves_sharp_cards", sharp_edge_energy=sharp_energy, blurred_edge_energy=blurred_energy)
        self.action("cancel"); self.settled(None)
        if self.args.video:
            self.video()

    def video(self):
        scenes = [("solid", {**DEFAULTS, "workspace_scale": 1.25}),
                  ("clear-overlay", {**DEFAULTS, "workspace_overlay": 1, "background_opacity": 0,
                                     "workspace_scale": 1.1, "reflection_opacity": 0, "show_labels": 0, "center_y": .5}),
                  ("blurred-tint", {**DEFAULTS, "workspace_overlay": 1, "background_opacity": .45,
                                    "background_color": "rgb(182030)", "background_blur": 16, "workspace_scale": 1.25,
                                    "border_width": 3, "border_color_focus": "rgb(40cda9) rgb(ecA06d) 45deg"})]
        recorder = None
        try:
            with (self.output / "recorder.log").open("w") as log:
                # Preserve capture timestamps under slow software rendering. A
                # forced recorder framerate compresses time when frames arrive late.
                recorder = subprocess.Popen(["wf-recorder", "-D", "-o", "WAYLAND-1", "-f", str(self.output / "configurations-raw.mp4")],
                                            env=HELPER["environment"](self.state), stdout=log, stderr=log)
            # Give screencopy/encoder startup time before timing the first preset,
            # including the emulated GPU used by the runtime proof.
            time.sleep(5)
            require(recorder.poll() is None, "Recorder failed to start")
            timeline = []
            started = time.monotonic()
            for index, (name, settings) in enumerate(scenes):
                self.settings(**settings)
                section = {"name": name, "settings": settings, "start_seconds": time.monotonic() - started}
                self.action("toggle"); self.settled(4)
                self.frame(f"02-{name}")
                time.sleep(.8)
                for destination in (5, 2, 4):
                    self.action("jump", destination); self.settled(destination)
                    time.sleep(.35)
                self.action("cancel"); self.settled(None)
                time.sleep(.5)
                section["end_seconds"] = time.monotonic() - started
                timeline.append(section)
            self.evidence["video_scenes"] = timeline
        finally:
            CAPTURE["stop_recorder"](recorder, self.evidence)
        self.record("three_configurations_recorded", scenes=[name for name, _ in scenes])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("output")
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--video", action="store_true")
    args = parser.parse_args()
    args.phase = "appearance"
    AppearanceProof(args).run()


if __name__ == "__main__":
    main()

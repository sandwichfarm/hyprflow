#!/usr/bin/env python3
"""Prove configuration against exact builds in one owned nested compositor.

Run baseline first, then load the candidate into that SAME session and run candidate.
Requires the existing seven calibration fixtures and installed grim / Pillow.
"""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import time

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
HELPER = runpy.run_path(str(ROOT / "scripts/nested-session.py"))
DEFAULTS = {"workspace_scale": 1.0, "workspace_spread": .18, "border_width": 0,
            "border_color": "rgba(ffffffff)", "border_color_current": "", "border_color_focus": ""}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lua(value):
    if isinstance(value, dict):
        return "{" + ",".join(f"{key}={lua(item)}" for key, item in value.items()) + "}"
    return json.dumps(value)


def longest_run(values):
    runs = []
    start = previous = None
    for value in values:
        if previous is None or value != previous + 1:
            if previous is not None:
                runs.append((start, previous + 1))
            start = value
        previous = value
    if previous is not None:
        runs.append((start, previous + 1))
    require(runs, "Expected colored pixels were absent")
    return max(runs, key=lambda item: item[1] - item[0])


class ConfigurationProof:
    def __init__(self, args):
        self.args = args
        self.state = HELPER["session"](args.directory)
        self.output = Path(args.output).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        require(not any(self.output.iterdir()), "Use an empty output directory to preserve previous evidence")
        self.artifact = Path(args.artifact).resolve()
        require(digest(self.artifact) == args.sha256, "Artifact differs from the approved SHA-256")
        identity = {key: self.state[key] for key in ("pid", "start_time", "signature")}
        self.evidence = {"passed": False, "phase": args.phase, "artifact_sha256": args.sha256,
                         "runtime_identity_sha256": hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(),
                         "checks": [], "frames": []}
        self.started = time.monotonic()
        self.initial_submap = self.control("submap")
        self.assert_mapping()

    def control(self, *args, check=True):
        HELPER["session"](self.args.directory)
        return HELPER["control"](self.state, *args, check=check).stdout.strip()

    def assert_mapping(self):
        lines = [line for line in Path(f'/proc/{self.state["pid"]}/maps').read_text().splitlines()
                 if line.split(maxsplit=5)[-1] == str(self.artifact)]
        require(lines and all(int(line.split()[4]) == self.artifact.stat().st_ino for line in lines),
                "Approved artifact inode is not mapped into the owned compositor")
        require(digest(self.artifact) == self.args.sha256, "Approved artifact changed during proof")
        self.evidence["artifact_mapping_verified"] = True

    def save(self):
        self.evidence["duration_seconds"] = round(time.monotonic() - self.started, 3)
        (self.output / "manifest.json").write_text(json.dumps(self.evidence, indent=2) + "\n")

    def record(self, name, **details):
        self.evidence["checks"].append({"name": name, "passed": True, **details})
        self.save()
        print(f"PASS {name}", flush=True)

    def status(self):
        return json.loads(self.control("repl", "return hl.plugin.hyprflow.status()"))

    def action(self, name, argument=None):
        self.control("repl", f"return hl.plugin.hyprflow.{name}({'' if argument is None else lua(argument)})")

    def settled(self, selected):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            actual = self.status()
            if selected is None and not actual["open"]:
                return actual
            if (selected is not None and actual.get("selected") == selected and not actual.get("closing", True)
                    and actual.get("openness", 0) >= .999999 and abs(actual["position"] - (selected - 1)) < .000001):
                time.sleep(.2)
                return actual
            time.sleep(.02)
        raise RuntimeError(f"Selection {selected} did not settle: {actual}")

    def reset(self):
        if self.status()["open"]:
            self.action("cancel")
            self.settled(None)
        self.control("reload")
        require(not self.control("configerrors"), "Nested config has errors after reload")
        self.control("dispatch", "hl.dsp.focus({ workspace = 4 })")
        self.initial_submap = self.control("submap")
        time.sleep(.2)

    def settings(self, **values):
        self.control("repl", f"return hl.config({lua({'plugin': {'hyprflow': values}})})")
        require(not self.control("configerrors"), "Valid configuration reported errors")
        time.sleep(.15)

    def frame(self, name):
        time.sleep(.2)
        path = self.output / f"{name}.png"
        subprocess.run(["grim", "-o", "WAYLAND-1", str(path)], env=HELPER["environment"](self.state), check=True, timeout=10)
        image = Image.open(path).convert("RGB")
        self.evidence["frames"].append({"file": path.name, "sha256": digest(path), "size": list(image.size)})
        self.save()
        return image

    def open_four(self):
        if not self.status()["open"]:
            self.action("toggle")
        else:
            self.action("jump", 4)
        self.settled(4)

    def prime_fixtures(self):
        require(not self.status()["open"], "Fixture priming requires closed flow")
        for selected in range(1, 8):
            self.control("dispatch", f"hl.dsp.focus({{ workspace = {selected} }})")
            time.sleep(.15)
        self.control("dispatch", "hl.dsp.focus({ workspace = 4 })")
        time.sleep(.2)

    def default_frames(self):
        self.reset()
        self.prime_fixtures()
        frames = {"closed": self.frame("default-closed")}
        self.open_four()
        for selected in (4, 1, 7):
            self.action("jump", selected)
            self.settled(selected)
            frames[str(selected)] = self.frame(f"default-{selected}")
        self.action("cancel")
        self.settled(None)
        closed = self.frame("default-cancelled")
        require(ImageChops.difference(frames["closed"], closed).getbbox() is None, "Default cancel did not restore the original image")
        self.record("default_cancel_restores_workspace")
        return frames

    def baseline(self):
        self.default_frames()
        missing = {}
        for key, value in DEFAULTS.items():
            before = self.control("getoption", "plugin:hyprflow:" + key)
            self.control("repl", f"return hl.config({lua({'plugin': {'hyprflow': {key: value}}})})", check=False)
            error = self.control("configerrors")
            require(before == "no such option" and "unknown config key" in error and key in error,
                    f"Baseline did not expose the expected missing option: {key}")
            missing[key] = {"getoption": before, "configuration_error": error}
            self.control("reload")
        self.record("new_configuration_contract_red_on_baseline", missing_options=missing)

    @staticmethod
    def bright_bounds(image):
        # The white calibration workspace, above the separate caption/reflection.
        width, height = image.size
        points = [(x, y) for y in range(int(height * .08), int(height * .68))
                  for x in range(int(width * .2), int(width * .8))
                  if min(image.getpixel((x, y))) > 180]
        require(points, "Centered calibration workspace was not visible")
        return [min(x for x, _ in points), min(y for _, y in points), max(x for x, _ in points) + 1, max(y for _, y in points) + 1]

    @staticmethod
    def inactive_spacing(image):
        y = round(image.height * .4)
        orange = [x for x in range(image.width // 2) if (lambda c: c[0] > 90 and c[0] > c[1] * 1.5 and c[1] > c[2] * 1.6)(image.getpixel((x, y)))]
        green = [x for x in range(image.width // 2) if (lambda c: c[1] > 65 and c[1] > c[0] * 1.8 and c[2] > c[0] * 1.4)(image.getpixel((x, y)))]
        orange_run, green_run = longest_run(orange), longest_run(green)
        return {"orange": list(orange_run), "green": list(green_run), "spacing": green_run[0] - orange_run[0]}

    def geometry(self):
        self.open_four()
        bounds = {}
        for scale in (.7, 1.2):
            self.settings(workspace_scale=scale)
            bounds[str(scale)] = self.bright_bounds(self.frame(f"scale-{scale}"))
        small, large = bounds["0.7"], bounds["1.2"]
        width_ratio = (large[2] - large[0]) / (small[2] - small[0])
        height_ratio = (large[3] - large[1]) / (small[3] - small[1])
        require(abs(width_ratio - 1.2 / .7) < .02 and abs(height_ratio - 1.2 / .7) < .02,
                "Visible workspace size did not follow workspace_scale")
        self.record("workspace_scale_updates_open_flow", measured_bounds=bounds, width_ratio=width_ratio, height_ratio=height_ratio)
        self.settings(workspace_scale=1)
        spacing = {}
        for spread in (.05, .3):
            self.settings(workspace_spread=spread)
            frame = self.frame(f"spread-{spread}")
            spacing[str(spread)] = self.inactive_spacing(frame)
            require(self.bright_bounds(frame) == self.bright_bounds(Image.open(self.output / "default-4.png").convert("RGB")),
                    "Inactive spread changed the centered workspace size")
        side = min(.58 * frame.height, .38 * frame.width)
        require(abs(spacing["0.3"]["spacing"] - spacing["0.05"]["spacing"] - side * .25) < 3,
                "Visible inactive spacing did not follow the configured card-width distance")
        self.record("workspace_spread_updates_open_flow", measured=spacing, expected_difference=side * .25)
        self.settings(workspace_spread=.18)

    @staticmethod
    def red_run(image):
        return longest_run([y for y in range(round(image.height * .02), round(image.height * .24))
                            if (lambda c: c[0] > 180 and c[1] < 60 and c[2] < 60)(image.getpixel((image.width // 2, y)))])

    def borders(self):
        self.settings(border_color="rgba(ff0000ff)", border_width=2)
        thin = self.frame("border-solid-2")
        thin_run = self.red_run(thin)
        self.settings(border_width=8)
        solid = self.frame("border-solid-8")
        solid_run = self.red_run(solid)
        require(1 <= thin_run[1] - thin_run[0] <= 3 and 7 <= solid_run[1] - solid_run[0] <= 9,
                f"Border thickness did not match logical pixels: {thin_run}, {solid_run}")
        self.record("solid_border_width", thin=list(thin_run), thick=list(solid_run))
        x, y = solid.width // 2, (solid_run[0] + solid_run[1]) // 2
        self.settings(border_color="rgba(ff000080)")
        alpha = self.frame("border-alpha")
        sample = alpha.getpixel((x, y))
        require(110 <= sample[0] <= 145 and sample[1] < 20 and sample[2] < 20, f"Border alpha was not blended: {sample}")
        self.record("border_alpha", sample=list(sample))
        self.settings(border_color="rgba(ff0000ff) rgba(0000ffff) 0deg")
        horizontal = self.frame("border-gradient-0")
        self.settings(border_color="rgba(ff0000ff) rgba(0000ffff) 90deg")
        vertical = self.frame("border-gradient-90")
        left, right = horizontal.getpixel((x - 100, y)), horizontal.getpixel((x + 100, y))
        vertical_left, vertical_right = vertical.getpixel((x - 100, y)), vertical.getpixel((x + 100, y))
        require(abs(left[0] - right[0]) > 50 and abs(left[2] - right[2]) > 50,
                "Multicolor border did not interpolate across its horizontal edge")
        require(max(abs(a - b) for a, b in zip(vertical_left, vertical_right)) < 5,
                "Gradient angle did not rotate its color interpolation")
        self.record("multicolor_border_and_angle", horizontal=[list(left), list(right)], vertical=[list(vertical_left), list(vertical_right)])
        for count, colors in ((3, ["ff0000", "00ff00", "0000ff"]),
                              (10, ["ff0000"] * 3 + ["00ff00"] * 3 + ["0000ff"] * 4)):
            self.settings(border_color=" ".join(f"rgb({color})" for color in colors) + " 0deg")
            multicolor = self.frame(f"border-gradient-{count}-stops")
            side = min(.58 * multicolor.height, .38 * multicolor.width)
            samples = [multicolor.getpixel((round(x + side * offset), y)) for offset in (-.45, 0, .45)]
            require(samples[0][0] > 180 and samples[1][1] > 180 and samples[2][2] > 180,
                    f"{count}-stop gradient lost its red, green, or blue color stop")
            require(samples[1][0] < 90 and samples[1][2] < 90, f"{count}-stop gradient did not retain its middle green stop")
            self.record(f"gradient_{count}_stops", samples=[list(sample) for sample in samples])
        for first_angle, second_angle in (("45.9deg", "45deg"), ("-45deg", "315deg")):
            prefix = "rgba(ff0000ff) rgba(0000ffff) "
            self.settings(border_color=prefix + first_angle)
            first_angle_image = self.frame("border-angle-" + first_angle)
            self.settings(border_color=prefix + second_angle)
            second_angle_image = self.frame("border-angle-" + second_angle)
            require(ImageChops.difference(first_angle_image, second_angle_image).getbbox() is None,
                    f"Native angle normalization differs: {first_angle} / {second_angle}")
            self.record("native_angle_equivalence", angles=[first_angle, second_angle])
        for index, color in enumerate(("rgb(ff0000)", "rgba(ff0000ff)", "0xffff0000")):
            self.settings(border_color=color)
            equivalent = self.frame(f"border-color-notation-{index}")
            require(ImageChops.difference(solid, equivalent).getbbox() is None, f"Color notation changed channel order: {color}")
        self.record("rgb_rgba_argb_color_equivalence")
        self.settings(border_color="rgba(ff0000ff)", border_color_current="rgba(0000ffff)", border_color_focus="rgba(00ff00ff)")
        overlap = self.frame("border-focus-over-current")
        color = overlap.getpixel((x, y))
        require(color[1] > 220 and color[0] < 20 and color[2] < 20, "Focus override did not win over current override")
        self.action("jump", 5)
        self.settled(5)
        priority = self.frame("border-current-and-focus")
        require(priority.getpixel((x, y))[1] > 220, "Focused workspace did not use focus border")
        blue_count = sum(1 for py in range(40, 500) for px in range(0, x - 200)
                         if (lambda c: c[2] > 100 and c[2] > max(c[0], c[1]) * 3)(priority.getpixel((px, py))))
        require(blue_count > 100, "Origin workspace did not retain its current border")
        self.settings(border_color_focus="")
        inherited = self.frame("border-focus-inherits-base")
        require(inherited.getpixel((x, y))[0] > 220 and inherited.getpixel((x, y))[1] < 20,
                "Empty focus override did not inherit base border")
        self.action("jump", 4)
        self.settled(4)
        current = self.frame("border-current-inherits-priority")
        require(current.getpixel((x, y))[2] > 220, "Current override did not apply with an empty focus override")
        self.settings(border_color_current="")
        base = self.frame("border-inherit-base")
        require(base.getpixel((x, y))[0] > 220, "Empty current override did not inherit base border")
        self.record("border_current_focus_precedence_and_inheritance", current_blue_pixels=blue_count)
        self.settings(border_width=0)
        disabled = self.frame("border-disabled")
        baseline = Image.open(self.output / "default-4.png").convert("RGB")
        require(ImageChops.difference(disabled, baseline).getbbox() is None, "Zero border width did not restore the exact default image")
        self.record("zero_border_width_restores_defaults")

    def invalid(self):
        # Follow the in-memory log so asynchronous native file flushing and
        # bounded rolling-log history cannot hide or duplicate diagnostics.
        logfile = Path(self.state["directory"]) / f"configuration-diagnostics-{time.time_ns()}.log"
        with logfile.open("wb") as stream:
            follower = subprocess.Popen(["stdbuf", "-oL", "hyprctl", "-i", self.state["signature"], "rollinglog", "-f"],
                                        env=HELPER["environment"](self.state), stdout=stream, stderr=subprocess.STDOUT)
            try:
                time.sleep(.1)
                require(follower.poll() is None, "Owned rolling-log follower did not start")
                self.invalid_values(logfile)
                require(follower.poll() is None, "Owned rolling-log follower exited during verification")
                self.evidence["diagnostic_source"] = "Line-buffered hyprctl rollinglog --follow from the owned compositor"
            finally:
                follower.terminate()
                follower.wait(timeout=5)

    def invalid_values(self, logfile):
        # This Hyprland Lua bridge stores raw values without enforcing the V2
        # validators. Verify rejection at the plugin's application boundary.
        invalid = {"workspace_scale": [.09, 2.01, "bad"], "workspace_spread": [-.01, 1.01, "bad"],
                   "border_width": [-1, 33, "bad"], "border_color": ["not-a-color", "rgba(ff0000ff) nope", "rgba(ff0000ff) " * 11,
                                        "rgba(ff0000gg)", "rgba(ff0000ff", "rgba(ff0000ff) 45deg junk",
                                        "rgba(ff0000ff) nandeg", "rgba(ff0000ff) infdeg", "45deg"],
                   "border_color_current": ["not-a-color"], "border_color_focus": ["not-a-color"]}
        cases = [(key, value, lua(value)) for key, values in invalid.items() for value in values]
        cases += [(key, expression, expression) for key in ("workspace_scale", "workspace_spread")
                  for expression in ("0/0", "math.huge", "-math.huge")]
        good_values = {"workspace_scale": .8, "workspace_spread": .14, "border_width": 8,
                       "border_color": "rgba(ff0000ff)", "border_color_current": "rgba(0000ffff)", "border_color_focus": "rgba(00ff00ff)"}
        results = []
        for index, (key, value, expression) in enumerate(cases):
            self.control("reload")
            self.settings(**good_values)
            self.action("jump", 5)
            self.settled(5)
            good = self.frame(f"invalid-{index:02d}-last-good")
            before = self.control("getoption", "plugin:hyprflow:" + key)
            offset = logfile.stat().st_size
            command = "return hl.config({plugin={hyprflow={" + key + "=" + expression + "}}})"
            self.control("repl", command, check=False)
            error = self.control("configerrors")
            raw = self.control("getoption", "plugin:hyprflow:" + key)
            if error:
                require(raw == before, f"Native rejection replaced the last good {key} value")
                results.append({"key": key, "value": value, "native_error": error, "retained_last_good": True})
                continue
            prefix = f"[hyprflow] rejected {key}:"
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                diagnostics = logfile.read_bytes()[offset:].decode(errors="replace")
                if prefix in diagnostics:
                    break
                time.sleep(.1)
            require(prefix in diagnostics, f"Invalid {key} was stored without a plugin rejection diagnostic")
            self.control("dismissnotify", "-1")
            actual = self.frame(f"invalid-{index:02d}-retained")
            require(ImageChops.difference(good, actual).getbbox() is None, f"Invalid {key} changed last-good rendered geometry or borders")
            details = {"key": key, "value": value, "host_raw_option": raw, "retained_last_good_rendering": True,
                       "diagnostic": next(line[line.index(prefix):] for line in diagnostics.splitlines() if prefix in line)}
            if (key, value) in (("workspace_scale", .09), ("border_color", "not-a-color")):
                self.control("repl", command, check=False)
                time.sleep(1)
                once = logfile.read_bytes()[offset:].decode(errors="replace").count(prefix)
                require(once == 1, f"Unchanged invalid {key} emitted repeated rejection diagnostics")
                self.settings(**{key: good_values[key]})
                self.control("repl", command, check=False)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    twice = logfile.read_bytes()[offset:].decode(errors="replace").count(prefix)
                    if twice >= 2:
                        break
                    time.sleep(.1)
                require(twice == 2, f"New invalid {key} episode did not emit a fresh diagnostic")
                self.control("dismissnotify", "-1")
                details["diagnostics_once_per_rejected_episode"] = [once, twice]
            results.append(details)
            self.evidence["invalid_configuration_cases"] = results
            self.save()
        self.control("reload")
        require(not self.control("configerrors"), "Errors persisted after clean reload")
        self.record("invalid_configuration_rejected_at_application_boundary", cases=results,
                    host_lua_limitation="Raw getoption may show rejected values; plugin retains last good appearance and emits diagnostics")

    def invalid_reload_closed(self):
        self.reset()
        config = Path(self.state["directory"]) / "nested.lua"
        original = config.read_bytes()
        prefixes = [f"[hyprflow] rejected {key}:" for key in ("workspace_scale", "border_color")]
        before_log = self.control("rollinglog")
        try:
            config.write_bytes(original + b'\nhl.config({plugin={hyprflow={workspace_scale=0.09,border_color="bad-color"}}})\n')
            self.control("reload")
            require(not self.status()["open"], "Config reload unexpectedly opened flow")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                # The disk log can remain buffered while the compositor is idle.
                diagnostics = self.control("rollinglog")
                if all(diagnostics.count(prefix) > before_log.count(prefix) for prefix in prefixes):
                    break
                time.sleep(.1)
            require(all(diagnostics.count(prefix) > before_log.count(prefix) for prefix in prefixes),
                    "Closed config reload failed to report fresh rejected-appearance diagnostics")
            self.control("dismissnotify", "-1")
            self.record("invalid_configuration_reload_while_closed", diagnosed_options=["workspace_scale", "border_color"], flow_open=False)
        finally:
            config.write_bytes(original)
            self.control("reload")

    def sample_configuration(self):
        self.reset()
        config = Path(self.state["directory"]) / "nested.lua"
        original = config.read_bytes()
        example = ROOT / "config/hyprflow.lua"
        try:
            config.write_bytes(original + ("\ndofile(" + lua(str(example)) + ")\n").encode())
            self.control("reload")
            require(not self.control("configerrors"), "Documented configuration example produced errors")
            require(not self.status()["open"], "Sourcing the example unexpectedly opened flow")
            values = {}
            for key, expected in DEFAULTS.items():
                raw = self.control("getoption", "plugin:hyprflow:" + key)
                actual = raw.splitlines()[0].split(":", 1)[1].strip()
                require((actual == expected if isinstance(expected, str) else float(actual) == expected),
                        f"Configuration example changed the default {key}")
                values[key] = raw
            require(self.control("getoption", "plugin:hyprflow:workspace_count").startswith("int: 9"),
                    "Configuration example changed the workspace count")
            self.record("documented_lua_configuration_loads", file="config/hyprflow.lua", sha256=digest(example), options=values)
        finally:
            config.write_bytes(original)
            self.control("reload")

    def lifecycle(self):
        config = Path(self.state["directory"]) / "nested.lua"
        original = config.read_bytes()
        try:
            values = {"workspace_scale": .85, "workspace_spread": .12, "border_width": 5,
                      "border_color": "rgba(ff8800ff) rgba(0088ffff) 45deg"}
            config.write_bytes(original + ("\nhl.config(" + lua({"plugin": {"hyprflow": values}}) + ")\n").encode())
            if self.status()["open"]:
                self.action("cancel")
                self.settled(None)
            self.control("reload")
            self.prime_fixtures()
            self.open_four()
            first = self.frame("reload-configured")
            self.control("reload")
            self.settled(4)
            second = self.frame("reload-configured-repeat")
            require(ImageChops.difference(first, second).getbbox() is None, "Config reload changed settled custom rendering")
            require(self.control("submap") == "hyprflow", "Config reload lost modal submap")
            require(not self.control("configerrors"), "Custom reload has errors")
            self.record("custom_configuration_reload_while_open")
            for index in range(3):
                self.control("plugin", "unload", str(self.artifact))
                require("hyprflow" not in self.control("plugin", "list").lower(), "Plugin remained registered after unload")
                require(self.control("submap") == self.initial_submap, "Unload did not restore the original submap")
                require(json.loads(self.control("-j", "activeworkspace"))["id"] == 4, "Unload changed origin workspace")
                self.control("plugin", "load", str(self.artifact))
                self.control("reload")
                self.assert_mapping()
                require(not self.status()["open"], "Reload restored stale open state")
                self.prime_fixtures()
                self.open_four()
                restored = self.frame(f"reload-plugin-{index + 1}")
                require(ImageChops.difference(first, restored).getbbox() is None, "Reloaded configuration or rendering differs")
            self.record("custom_configuration_unload_reload_three_cycles")
            self.action("jump", 5)
            self.settled(5)
            self.action("accept")
            self.settled(None)
            require(json.loads(self.control("-j", "activeworkspace"))["id"] == 5, "Custom border accept did not select workspace 5")
            self.frame("custom-accepted")
            self.control("dispatch", "hl.dsp.focus({ workspace = 4 })")
            self.open_four()
            self.action("cancel")
            self.settled(None)
            restored = self.frame("custom-cancelled")
            original_frame = Image.open(self.output / "default-closed.png").convert("RGB")
            require(ImageChops.difference(restored, original_frame).getbbox() is None, "Custom cancel left residual borders or geometry")
            self.record("custom_configuration_accept_cancel_cleanup")
        finally:
            config.write_bytes(original)
            self.control("reload")

    def candidate(self):
        baseline = Path(self.args.baseline).resolve()
        old = json.loads((baseline / "manifest.json").read_text())
        require(old["passed"] and old["phase"] == "baseline", "Baseline receipt is incomplete")
        require(old["runtime_identity_sha256"] == self.evidence["runtime_identity_sha256"],
                "Candidate must use the exact baseline runtime and fixtures")
        self.evidence["baseline_artifact_sha256"] = old["artifact_sha256"]
        for key in DEFAULTS:
            require(self.control("getoption", "plugin:hyprflow:" + key) != "no such option", f"Missing option: {key}")
        self.record("all_configuration_options_registered")
        self.default_frames()
        compared = []
        for name in ("closed", "4", "1", "7", "cancelled"):
            filename = f"default-{name}.png"
            require((baseline / filename).read_bytes() == (self.output / filename).read_bytes(), f"Default PNG differs from baseline: {filename}")
            compared.append({"file": filename, "sha256": digest(self.output / filename), "byte_identical": True})
        self.record("default_images_byte_identical_to_baseline", frames=compared)
        self.geometry()
        self.borders()
        self.invalid()
        self.invalid_reload_closed()
        self.sample_configuration()
        self.lifecycle()

    def run(self):
        config = Path(self.state["directory"]) / "nested.lua"
        original_config = config.read_bytes()
        try:
            with HELPER["isolated_input"](self.state) as receipt:
                self.evidence["input_isolation"] = receipt
                # Cursor visibility also needs native reload refresh; changing its
                # Lua raw value alone can leave a software cursor in screencopies.
                config.write_bytes(config.read_bytes() + b"\nhl.config({cursor={invisible=true}})\n")
                self.evidence["cursor_isolation"] = "Owned nested config; restored on exit"
                if self.args.phase == "baseline":
                    self.baseline()
                else:
                    self.candidate()
                self.reset()
                self.assert_mapping()
                self.evidence["final_status"] = self.status()
                self.evidence["final_workspace"] = json.loads(self.control("-j", "activeworkspace"))["id"]
                self.evidence["configerrors"] = self.control("configerrors")
                require(not self.evidence["final_status"]["open"] and self.evidence["final_workspace"] == 4 and not self.evidence["configerrors"],
                        "Proof did not restore a clean closed flow")
            self.evidence["passed"] = True
        except Exception as error:
            self.evidence["error"] = str(error)
            raise
        finally:
            config.write_bytes(original_config)
            try:
                self.control("reload")
                self.evidence["owned_config_restored"] = config.read_bytes() == original_config
            except Exception as error:
                self.evidence["passed"] = False
                self.evidence["cleanup_error"] = str(error)
                raise
            finally:
                self.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("baseline", "candidate"))
    parser.add_argument("directory", help="Owned nested-session state directory")
    parser.add_argument("output", help="Empty output directory")
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--baseline", help="Completed baseline output directory, required for candidate")
    args = parser.parse_args()
    if args.phase == "candidate" and not args.baseline:
        parser.error("candidate requires --baseline")
    ConfigurationProof(args).run()


if __name__ == "__main__":
    main()

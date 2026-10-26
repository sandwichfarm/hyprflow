#!/usr/bin/env python3
"""Exercise effective output configuration and real capture endpoints in an owned session."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import time

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
BASE = runpy.run_path(str(ROOT / "scripts/verify-lifecycle.py"))
HELPER = BASE["HELPER"]
require = BASE["require"]


class RenderMatrix(BASE["LifecycleProof"]):
    def monitor(self):
        return next(m for m in self.query("monitors") if m["name"] == self.output_name)

    def configure(self, scale=1, transform=0, cm="srgb", bitdepth=8, force_hdr=False):
        rule = {"output": self.output_name, "mode": "1440x900@60", "position": "0x0",
                "scale": scale, "transform": transform, "cm": cm, "bitdepth": bitdepth,
                "supports_hdr": int(force_hdr), "supports_wide_color": int(force_hdr)}
        lua = runpy.run_path(str(ROOT / "scripts/verify-configuration.py"))["lua"]
        self.control("eval", f"hl.monitor({lua(rule)})")
        expected_cm = "srgb" if cm == "hdr" and not force_hdr else cm
        expected_format = "101010" if bitdepth == 10 else "8888"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            monitor = self.monitor()
            matches = (monitor["scale"] == scale and monitor["transform"] == transform
                       and (monitor["width"], monitor["height"]) == (1440, 900)
                       and monitor["colorManagementPreset"] == expected_cm
                       and expected_format in monitor["currentFormat"])
            if matches:
                break
            time.sleep(.05)
        require(matches, f"Output request not applied: {monitor}")
        require(not self.control("configerrors").stdout.strip(), "Output configuration error")
        # Startup/modeset notices fade independently of workspace pixels.
        self.control("dismissnotify", "-1")
        time.sleep(.3)
        return {"requested": rule, "effective": monitor}

    def frame(self, name):
        path = self.output / f"{name}.png"
        subprocess.run(["grim", "-o", self.output_name, str(path)], env=HELPER["environment"](self.state), check=True, timeout=10)
        image = Image.open(path).convert("RGB")
        require(max(ImageStat.Stat(image).stddev) > 5, f"Blank or uniform capture: {path.name}")
        self.evidence.setdefault("frames", []).append({"file": path.name,
                                                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                                       "size": list(image.size)})
        self.save()
        return image

    def endpoint(self, expected, name):
        actual = self.frame(name)
        require(actual.size == expected.size, "Endpoint dimensions changed")
        mean_error = sum(ImageStat.Stat(ImageChops.difference(actual, expected)).mean) / 3
        require(mean_error < .2, f"Native endpoint changed, mean channel error {mean_error}")
        return mean_error

    def scene(self, name):
        self.control("dispatch", "hl.dsp.focus({ workspace=5 })")
        time.sleep(.2)
        destination = self.frame(name + "-destination")
        self.focus_probe()
        time.sleep(.2)
        origin = self.frame(name + "-origin")
        self.action("toggle")
        self.settled(4)
        opened = self.frame(name + "-open")
        require(opened.size == origin.size, "Switcher capture output dimensions are wrong")
        difference = sum(ImageStat.Stat(ImageChops.difference(opened, origin)).mean) / 3
        require(difference > 2, "Open flow did not render over the native scene")
        self.action("jump", 5)
        self.settled(5)
        require(self.query("activeworkspace")["id"] == 4, "Capture changed native workspace prematurely")
        self.frame(name + "-selected")
        self.action("cancel")
        self.closed()
        cancel_error = self.endpoint(origin, name + "-cancel")
        self.action("jump", 5)
        self.settled(5)
        self.action("accept")
        self.closed()
        require(self.query("activeworkspace")["id"] == 5, "Acceptance selected the wrong workspace")
        accept_error = self.endpoint(destination, name + "-accept")
        self.focus_probe()
        self.record(name, size=list(opened.size), open_difference=difference,
                    cancel_mean_error=cancel_error, accept_mean_error=accept_error)

    def geometry(self):
        cases = [(1, 0), (1.25, 0), (1.5, 0), (2, 0)]
        if self.profile == "full":
            cases += [(1, 1), (1, 2), (1, 3), (1, 4), (1.25, 1)]
        for scale, transform in cases:
            receipt = self.configure(scale, transform)
            self.scene(f"scale-{scale}-transform-{transform}")
            self.evidence["checks"][-1]["output"] = receipt
            self.save()
        self.configure()
        self.action("toggle")
        self.settled(4)
        self.configure(1.5, 1 if self.profile == "full" else 0)
        self.settled(4)
        self.frame("reconfigure-open")
        self.action("cancel")
        self.closed()
        self.configure()
        self.record("scale-and-rotation-change-while-open" if self.profile == "full" else "scale-change-while-open")

    def colors(self):
        cases = [("wide", 8, False), ("srgb", 10, False), ("hdr", 10, False), ("hdr", 10, True)]
        if self.profile == "vulkan-sdr":
            cases = [("srgb", 8, False)]
        for cm, depth, forced in cases:
            receipt = self.configure(cm=cm, bitdepth=depth, force_hdr=forced)
            # Record actual backend negotiation. A requested mode alone is not HDR proof.
            self.scene(f"color-{cm}-{depth}-forced-{forced}")
            self.evidence["checks"][-1]["output"] = receipt
            self.save()
        self.configure()

    def multi_output(self):
        before = {m["name"] for m in self.query("monitors")}
        # Additional Wayland outputs create parent windows; headless keeps host workspace confinement.
        self.control("output", "create", "headless", "HF-MATRIX-SECOND")
        second = None
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                added = [m for m in self.query("monitors") if m["name"] not in before]
                if added:
                    second = added[0]["name"]
                    break
                time.sleep(.05)
            require(second, "Second virtual output did not appear")
            self.control("eval", 'hl.workspace_rule({workspace="20",monitor=' + json.dumps(second) + ',persistent=true})')
            deadline = time.monotonic() + 5
            workspace = None
            while time.monotonic() < deadline:
                workspace = next((w for w in self.query("workspaces") if w["id"] == 20), None)
                if workspace and workspace["monitor"] == second:
                    break
                time.sleep(.05)
            require(workspace and workspace["monitor"] == second, "Test workspace was not placed on second output")
            self.focus_probe()
            self.action("toggle")
            self.settled(4)
            result = self.control("repl", "local ok = pcall(function() hl.plugin.hyprflow.jump(20) end); return tostring(ok)")
            require(result.stdout.strip() == "false", "Cross-monitor workspace was selectable")
            require(self.status()["selected"] == 4, "Rejected cross-monitor jump changed selection")
            self.action("cancel")
            self.closed()
            self.control("dispatch", "hl.dsp.focus({monitor=" + json.dumps(second) + "})")
            require(self.query("activeworkspace")["monitor"] == second, "Second output did not gain focus")
            self.action("toggle")
            require(self.status()["open"], "Flow did not open on second output")
            self.control("output", "remove", second)
            second = None
            self.closed()
            self.focus_probe()
            require(self.control("submap").stdout.strip() == self.initial_submap, "Monitor removal lost submap")
            self.record("cross-monitor-exclusion-and-active-output-removal")
        finally:
            if second:
                self.control("output", "remove", second, check=False)
            self.focus_probe()

    def run(self):
        config = Path(self.state["directory"]) / "nested.lua"
        original = config.read_bytes()
        self.output_name = None
        try:
            monitors = self.query("monitors")
            require(len(monitors) == 1, "Begin with one owned nested output")
            self.output_name = monitors[0]["name"]
            if self.output_name.startswith("WAYLAND-"):
                # Match the parent window's real size so late configure events cannot reset test modes.
                HELPER["place"](self.state, size=(1440, 900))
            self.control("eval", 'hl.config({ general={ gaps_out=24 }, decoration={ rounding=12, '
                         'shadow={ enabled=true, range=18 }, blur={ enabled=true } } })')
            self.control("eval", 'hl.config({ plugin={ hyprflow={ workspace_overlay=1, '
                         'background_blur=12, background_opacity=0.3, border_width=3 } } })')
            self.start_probe()
            self.geometry()
            self.colors()
            self.multi_output()
            self.unload_cycles()
            self.evidence["passed"] = True
        except Exception as error:
            self.evidence["error"] = str(error)
            raise
        finally:
            try:
                if self.output_name:
                    self.configure()
                if self.process:
                    self.cleanup()
            except Exception as error:
                self.evidence["passed"] = False
                self.evidence["cleanup_error"] = str(error)
                raise
            finally:
                config.write_bytes(original)
                self.control("reload")
                self.evidence["duration_seconds"] = round(time.monotonic() - self.started, 3)
                self.save()
        print(self.output / "manifest.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("output")
    parser.add_argument("--profile", choices=("full", "vulkan-sdr"), default="full",
                        help="Full output matrix, or explicit SDR/unrotated scope of the patched Vulkan WIP")
    parser.add_argument("--artifact", default=str(ROOT / "build/hyprflow.so"))
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    proof = RenderMatrix(args)
    proof.profile = args.profile
    proof.evidence["profile"] = args.profile
    if args.profile == "vulkan-sdr":
        proof.evidence["limits"] = ["Native WIP rotated-output control fails without the plugin",
                                    "Native WIP HDR/FP16 and physical HDR scanout are not qualified"]
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

#!/usr/bin/env python3
"""Verify modifier-release selection with real chords in an owned nested session."""

import argparse
import json
from pathlib import Path
import runpy
import time

HERE = Path(__file__).resolve().parent
HELPER = runpy.run_path(str(HERE / "nested-session.py"))
KEYBOARD = runpy.run_path(str(HERE / "nested-key.py"))
PROOF = runpy.run_path(str(HERE / "capture-proof.py"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--artifact", type=Path, help="Also verify unloading the candidate while release selection is armed")
    args = parser.parse_args()
    state = HELPER["session"](args.directory)
    control = lambda *args: HELPER["control"](state, *args).stdout
    status = lambda: PROOF["status"](state)
    config = Path(args.directory) / "nested.lua"
    original = config.read_bytes()
    checks = []

    def settled(selected, workspace):
        actual, _ = PROOF["wait_settled"](state, selected, time.monotonic())
        active = json.loads(control("-j", "activeworkspace"))["id"]
        PROOF["verify_step"](actual, selected, workspace, active)

    def setting(enabled):
        control("eval", 'hl.config({ plugin={ hyprflow={ select_on_release=' + str(enabled).lower() + ' } } })')

    try:
        with HELPER["isolated_input"](state):
            config.write_text(config.read_text() + '''
-- Chords used only by the release-selection proof.
for _, chord in ipairs({"SUPER + Tab", "SUPER + ALT + Tab"}) do
    hl.bind(chord, function() hl.plugin.hyprflow.right() end)
end
hl.define_submap("hyprflow", function()
    hl.bind("SUPER + Tab", function() hl.plugin.hyprflow.right() end)
    hl.bind("SUPER + SHIFT + Tab", function() hl.plugin.hyprflow.left() end)
    hl.bind("Return", function() hl.plugin.hyprflow.accept() end, { ignore_mods=true })
    hl.bind("Escape", function() hl.plugin.hyprflow.cancel() end, { ignore_mods=true })
end)
''')
            control("reload")
            assert not control("configerrors").strip(), "Nested config errors"
            assert not status()["open"], "Start with the flow closed"
            control("dispatch", 'hl.dsp.focus({ workspace=4 })')
            assert json.loads(control("-j", "getoption", "plugin:hyprflow:select_on_release"))["bool"] is False

            with KEYBOARD["keyboard"](args.directory) as connection:
                serial = 7

                def mods(mask, locked=0):
                    nonlocal serial
                    KEYBOARD["send"](connection, 6, 2, b"".join(KEYBOARD["word"](n) for n in (mask, 0, locked, 0)))
                    serial += 1
                    KEYBOARD["roundtrip"](connection, serial)

                def key(name):
                    nonlocal serial
                    for pressed in (1, 0):
                        stamp = int(time.monotonic() * 1000) & 0xFFFFFFFF
                        data = b"".join(KEYBOARD["word"](n) for n in (stamp, KEYBOARD["KEYS"][name], pressed))
                        KEYBOARD["send"](connection, 6, 1, data)
                        serial += 1
                        KEYBOARD["roundtrip"](connection, serial)

                # No option configured: releasing the chord leaves the flow open.
                mods(64)
                key("Tab")
                mods(0)
                settled(5, 4)
                key("Escape")
                settled(None, 4)
                checks.append("default false leaves flow open")

                setting(True)
                mods(64)
                key("Tab")
                settled(5, 4)
                checks.append("Tab release with Super held leaves flow open")
                key("Tab")
                settled(6, 4)
                mods(65)  # A later Shift is not part of the opening chord.
                key("Tab")
                settled(5, 4)
                mods(1)
                settled(None, 5)
                mods(0)
                checks.append("cycling and reverse cycling accept on opening modifier release")

                control("dispatch", 'hl.dsp.focus({ workspace=4 })')
                mods(72)
                key("Tab")
                mods(64)
                settled(5, 4)
                mods(0)
                settled(None, 5)
                checks.append("multi-modifier chord waits for last opening modifier")

                control("dispatch", 'hl.dsp.focus({ workspace=4 })')
                mods(64)
                key("Tab")
                mods(0)  # Release before the entry/navigation springs settle.
                settled(None, 5)
                checks.append("quick release commits pending destination")

                control("dispatch", 'hl.dsp.focus({ workspace=4 })')
                mods(64)
                key("Tab")
                key("Escape")
                mods(0)
                settled(None, 4)
                checks.append("Escape while modifier held cancels without release overriding")

                mods(64)
                key("Tab")
                control("eval", "hl.plugin.hyprflow.toggle()")
                mods(0)
                settled(None, 4)
                checks.append("explicit toggle disarms automatic acceptance")

                mods(64)
                key("Tab")
                key("Return")
                mods(0)
                settled(None, 5)
                checks.append("explicit accept still works")

                control("dispatch", 'hl.dsp.focus({ workspace=4 })')
                key("F10")
                key("Right")
                settled(5, 4)
                mods(64)
                mods(0)
                settled(5, 4)
                key("Escape")
                settled(None, 4)
                checks.append("unmodified opening does not arm on later modifiers")

                mods(0, locked=2)  # Caps Lock must not arm release selection.
                key("F10")
                mods(0)
                settled(4, 4)
                key("Escape")
                settled(None, 4)
                checks.append("lock state does not arm selection")

                # Failed opening must not leave an armed listener for a later flow.
                mods(64)
                HELPER["control"](state, "eval", 'hl.plugin.hyprflow.jump("absent-release-test")', check=False)
                assert not status()["open"]
                mods(0)
                key("F10")
                settled(4, 4)
                key("Escape")
                settled(None, 4)
                checks.append("failed jump clears release state")

                if args.artifact:
                    artifact = str(args.artifact.resolve(strict=True))
                    mods(64)
                    key("Tab")
                    control("plugin", "unload", artifact)
                    mods(0)
                    control("plugin", "load", artifact)
                    assert not status()["open"]
                    key("F10")
                    settled(4, 4)
                    key("Escape")
                    settled(None, 4)
                    checks.append("unload while armed removes listeners and restores submap")

            assert not control("configerrors").strip()
    finally:
        try:
            control("eval", "hl.plugin.hyprflow.cancel()")
            PROOF["wait_settled"](state, None, time.monotonic())
        finally:
            config.write_bytes(original)
            control("reload")
    print(json.dumps({"passed": True, "checks": checks}, indent=2))


if __name__ == "__main__":
    main()

# Experimental Vulkan runtime

This is an isolated qualification environment, not an installation or upgrade
for the daily desktop. Build the pinned runtime and development headers using
[the relocatable recipe](QUALIFICATION_PREPARE.md) and its adjacent patches.
Copy those files into a disposable directory before running its commands.
The [preparation manifest](preparation-manifest.json) and
[checksums](SHA256SUMS.json) identify the measured source, repairs, and baseline.

The [native rotation control](baseline/native-rotation/summary-public.json) fails without
the plugin. Vulkan qualification is SDR and unrotated; do not substitute the full
OpenGL output matrix or claim physical HDR support.

## Launch through the owned-session helper

From the isolated Hyprflow checkout, use `runtime_root` from the build recipe and
set `amd_render_node` to this machine's AMD **render** node. The private backend
validates its vendor and never acquires DRM master or a physical display.
The explicit `render_env` matters: the workspace-confined launcher inherits the
parent compositor's environment, not arbitrary variables from a caller's shell.

```sh
session_dir=$(python3 - "$runtime_root" "$amd_render_node" <<'PY' | python3 -c 'import json,sys; print(json.load(sys.stdin)["directory"])'
from pathlib import Path
import runpy
import sys

runtime = Path(sys.argv[1]).resolve()
config = runtime / "nested-vulkan.lua"
config.write_text(Path("config/nested.lua").read_text()
                  + '\nhl.config({render={use_vulkan=true,use_fp16=0}})\n')
helper = runpy.run_path("scripts/nested-session.py")
helper["start"](
    config=config,
    compositor=runtime / "hyprland/build/Hyprland",
    render_env={
        "LD_LIBRARY_PATH": str(runtime / "aquamarine/prefix/lib"),
        "HYPRFLOW_TEST_RENDER_NODE": sys.argv[2],
        "HYPRFLOW_TEST_HEADLESS_ONLY": "1",
        "VK_DRIVER_FILES": "/usr/share/vulkan/icd.d/radeon_icd.json",
        "VK_LOADER_LAYERS_DISABLE": "~implicit~",
        "__EGL_VENDOR_LIBRARY_FILENAMES": "/usr/share/glvnd/egl_vendor.d/50_mesa.json",
    },
    headless=True,
)
PY
)
trap 'python3 scripts/nested-session.py stop "$session_dir"' EXIT
```

First verify native rendering, reloads, and a nonempty native screenshot without
the plugin loaded. The package retains a [historical native core/sync baseline](baseline/native-core-sync-historical/summary-public.json)
and [REPL/watchdog proof](baseline/repl-manifest.json); the manifest labels their
exact earlier runtime versions. The [historical component regression](baseline/pre-blur-component-regression.json)
checks the qualification ABI, inactive captures, and native config-error rendering.
Run `verify-native.py` from this package for a fresh native-only baseline on your build.

Then load the separately built library and run the proofs:

```sh
artifact="$PWD/build-vulkan/hyprflow.so"
artifact_sha=$(sha256sum "$artifact" | cut -d' ' -f1)
python3 scripts/nested-session.py fixtures "$session_dir" --calibration
python3 scripts/nested-session.py ctl "$session_dir" plugin load "$artifact"
python3 scripts/verify-render-matrix.py "$session_dir" /tmp/hyprflow-vulkan-proof/matrix \
    --profile vulkan-sdr --artifact "$artifact" --sha256 "$artifact_sha"
python3 scripts/verify-appearance.py "$session_dir" /tmp/hyprflow-vulkan-proof/appearance \
    --artifact "$artifact" --sha256 "$artifact_sha"
python3 scripts/verify-select-on-release.py "$session_dir" --artifact "$artifact"
python3 scripts/verify-input.py "$session_dir" /tmp/hyprflow-vulkan-proof/input
python3 scripts/verify-lifecycle.py "$session_dir" /tmp/hyprflow-vulkan-proof/lifecycle \
    --artifact "$artifact" --sha256 "$artifact_sha"
```

The matrix preserves shadows and blur while stressing output changes. The
appearance proof temporarily removes fixture gaps and rounding so its white
calibration rectangle measures the workspace boundary, then restores the owned
configuration. It changes test fixtures for the detailed blur phase.

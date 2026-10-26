# Rebuild the experimental Vulkan test runtime

Run this from a disposable directory. These commands build local artifacts only;
they never install system packages or change a daily Hyprland session.
The patches beside this recipe apply only to the isolated test dependencies.

Prerequisites: CMake 3.30+, Ninja, a C++26-capable compiler, the usual Hyprland
build dependencies, glslang development headers/libraries, and Vulkan loader.
The qualification run used Aquamarine 0.15.0, hyprutils 0.14.1, hyprgraphics 0.5.1,
hyprlang 0.6.8, hyprcursor 0.1.13, Mesa 26.2.2 RADV and Vulkan loader 1.4.357.
Vulkan-Headers is fetched locally below because it was absent on the test host.

```sh
runtime_root="$PWD/vulkan-runtime"
recipe_dir="$PWD"
mkdir -p "$runtime_root"
git init "$runtime_root/hyprland"
git -C "$runtime_root/hyprland" fetch --depth 1 https://github.com/hyprwm/Hyprland.git b60bb19e8c8f5005a121714520acf41bd095e74b
git -C "$runtime_root/hyprland" checkout --detach FETCH_HEAD
git -C "$runtime_root/hyprland" submodule update --init --depth 1 subprojects/udis86 subprojects/hyprland-protocols
git -C "$runtime_root/hyprland" apply "$recipe_dir/qualification.patch"
git clone --depth 1 --branch v1.4.357 https://github.com/KhronosGroup/Vulkan-Headers.git "$runtime_root/vulkan-headers"
git clone --depth 1 --branch v0.15.0 https://github.com/hyprwm/aquamarine.git "$runtime_root/aquamarine"
git -C "$runtime_root/aquamarine" apply "$recipe_dir/qualification-aquamarine.patch"
cmake -S "$runtime_root/aquamarine" -B "$runtime_root/aquamarine/build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$runtime_root/aquamarine/prefix" -DBUILD_TESTING=OFF
cmake --build "$runtime_root/aquamarine/build" -j2
cmake --install "$runtime_root/aquamarine/build"
cmake -S "$runtime_root/hyprland" -B "$runtime_root/hyprland/build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$runtime_root/hyprland/prefix" -DNO_SYSTEMD=ON -DNO_TRACY=ON -DNO_HYPRPM=ON -DVulkan_INCLUDE_DIR="$runtime_root/vulkan-headers/include"
cmake --build "$runtime_root/hyprland/build" -j2 --target Hyprland

# Expose the exact generated headers through a local pkg-config overlay.
python3 - "$runtime_root" <<'PYOVERLAY'
from pathlib import Path
import re
import sys
root = Path(sys.argv[1]).resolve()
checkout = root / "hyprland"
header = (checkout / "src/plugins/PluginAPI.hpp").read_text()
assert 'HYPRFLOW_VULKAN_QUALIFICATION_ABI = "_hyprflow_vulkan_qualification_v1"' in header
overlay = checkout / "build/include-overlay"
overlay.mkdir(parents=True, exist_ok=True)
link = overlay / "hyprland"
if not link.exists():
    link.symlink_to(checkout, target_is_directory=True)
pc = (checkout / "build/hyprland.pc").read_text()
pc = re.sub(r"^prefix=.*$", "prefix=" + str(overlay), pc, flags=re.MULTILINE)
pc = pc.replace("Cflags: ", "Cflags: -I" + str(root / "vulkan-headers/include") + " ")
output = checkout / "build/pkgconfig"
output.mkdir(exist_ok=True)
(output / "hyprland.pc").write_text(pc)
PYOVERLAY
```

From the Hyprflow checkout, build its experimental artifact using only that
matching header overlay. Keep its objects separate from the stable OpenGL build:

```sh
PKG_CONFIG_PATH="$runtime_root/hyprland/build/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}" \
    make -j2 VULKAN=1 BUILD_DIR=build-vulkan-qualification-v1
```

The plugin artifact is `build-vulkan-qualification-v1/hyprflow.so`. Use a fresh
object directory when changing the private SDK. Never rebuild a mapped library;
unload it first or load an immutable copy. The overlay points at the actual
checkout, generated `protocols/` headers and fetched Vulkan headers. No generated
header files need to be included in the source patch.

## Local validation layer

Qualification uses Khronos core and synchronization validation, not only a
successful screenshot. On the Arch test host the following pinned package was
verified and extracted into the disposable prefix; nothing is installed into the
system. It requires the installed Arch signing keyring and compatible system
libraries. Recheck `ldd -r` if reproducing on a different environment.

```sh
validation_dir="$runtime_root/validation"
mkdir -p "$validation_dir/prefix"
layer_url=https://archive.archlinux.org/packages/v/vulkan-validation-layers/vulkan-validation-layers-1.4.357.0-1-x86_64.pkg.tar.zst
curl --fail --location --proto '=https' --output "$validation_dir/layers.pkg.tar.zst" "$layer_url"
curl --fail --location --proto '=https' --output "$validation_dir/layers.pkg.tar.zst.sig" "$layer_url.sig"
printf '%s  %s\n' 6f24c667b61e374b88789950f15e819cf4b32e9a1297a525520eed53d4077cf9 "$validation_dir/layers.pkg.tar.zst" | sha256sum --check -
gpgv --keyring /usr/share/pacman/keyrings/archlinux.gpg "$validation_dir/layers.pkg.tar.zst.sig" "$validation_dir/layers.pkg.tar.zst"
bsdtar --extract --file "$validation_dir/layers.pkg.tar.zst" --directory "$validation_dir/prefix"
ldd -r "$validation_dir/prefix/usr/lib/libVkLayer_khronos_validation.so"
cat > "$validation_dir/vk_layer_settings.txt" <<'VVLSETTINGS'
khronos_validation.validate_core = true
khronos_validation.validate_sync = true
khronos_validation.syncval_submit_time_validation = true
khronos_validation.gpuav_enable = false
khronos_validation.report_flags = error,warn
khronos_validation.debug_action = VK_DBG_LAYER_ACTION_LOG_MSG
VVLSETTINGS
```

GPU-assisted validation is not enabled. The opt-in
`HYPRFLOW_TEST_VALIDATION_ABORT=1` launch setting enables DebugUtils in release
builds and logs/aborts on the first validation ERROR before invalid work reaches
the driver. It does not suppress errors or turn failed tests into passes. A historical native-only failure receipt
and actual validation-error headers are retained as a positive control; they are
not current passing results.

## Qualification SDK identity

The Hyprland source is upstream PR #13272, not a stable release. Its `VERSION`
is 0.55.0 and its upstream base commit is
`b60bb19e8c8f5005a121714520acf41bd095e74b`. That commit and `pkg-config` version
alone do not identify this SDK: the private patches change native renderer and
command-buffer layouts.

`PluginAPI.hpp` defines `HYPRFLOW_VULKAN_QUALIFICATION_ABI` as
`_hyprflow_vulkan_qualification_v1`. Both the compositor server hash and the
header's inline client hash append this suffix. On the qualified dependency
versions the hashes are:

- Upstream base API hash: `b60bb19e8c8f5005a121714520acf41bd095e74b_aq_0.15_hu_0.14_hg_0.5_hc_0.1_hlg_0.6`.
- Qualified SDK API hash: `b60bb19e8c8f5005a121714520acf41bd095e74b_aq_0.15_hu_0.14_hg_0.5_hc_0.1_hlg_0.6_hyprflow_vulkan_qualification_v1`.

Build both compositor and plugins from the complete qualification SDK. Plugins
from the unpatched same-base fork or pre-suffix qualification builds are ABI
incompatible; old pre-suffix load attempts were explicitly rejected. Later
cpp-only fixes retain ABI v1 when headers/layouts do not change, so the suffix
alone does not identify the newest qualified executable: also check the exact
native binary and full patch hashes in the manifest. Bump the qualification suffix and rebuild both sides whenever private
ABI layouts change. Do not bypass the API guard or claim release 0.56.2 Vulkan
support from this runtime.
The runtime patch updates pointer conversions and stale identity comparisons,
removes an invalid shared lock on uniquely owned animation variables, fixes
phantom DRM-modifier records and Vulkan image-create chain lifetimes, repairs
stale shader interfaces, retains actual native frames for SDR screencopy, and
adds strict headless-only qualification mode, fixes target framebuffer color
metadata, selects supported stencil formats, repairs attachment access barriers
and full-scope staging/render timeline signals and waits, and submits retained
native frames in their sampled layout. It also backports value-returning REPL
IPC for the automated suite. The REPL adds no configuration-manager fields,
preserves ordinary eval's discarded-return behavior and configuration errors,
restores the original Lua stack depth on every exit, and runs both chunks and
return-value stringification under the existing 250 ms watchdog. It returns
values rather than capturing a global print stream. These are private upstream-WIP
repairs, not changes installed in the desktop compositor. The Aquamarine patch
adds an opt-in AMD render-node override for test processes.
Vulkan-Headers v1.4.357 resolves to commit e3b1eec08173d6b825cd3ac88c885a63b621504a
(annotated tag object 354fab82dbd91d2526a41ee4dbfff1012a623798).

From the Hyprflow checkout, launch through the owned-session helper. This
copies its test configuration into the disposable runtime and passes GPU and
loader overrides only to the test process. Select the AMD render node for the
test machine before running it:

```sh
owned_config="$runtime_root/nested-vulkan.lua"
cp config/nested.lua "$owned_config"
cat >> "$owned_config" <<'LUAQUAL'
hl.config({ render = { use_vulkan = true, use_fp16 = 0 } })
LUAQUAL
python3 - "$runtime_root" "$owned_config" > "$runtime_root/session.json" <<'PYSESSION'
from pathlib import Path
import runpy
import sys
runtime = Path(sys.argv[1]).resolve()
helper = runpy.run_path("scripts/nested-session.py")
helper["start"](
    config=Path(sys.argv[2]).resolve(),
    compositor=runtime / "hyprland/build/Hyprland",
    render_env={
        "LD_LIBRARY_PATH": str(runtime / "validation/prefix/usr/lib") + ":" + str(runtime / "aquamarine/prefix/lib"),
        "HYPRFLOW_TEST_RENDER_NODE": "/dev/dri/renderD129",
        "HYPRFLOW_TEST_HEADLESS_ONLY": "1",
        "HYPRFLOW_TEST_VALIDATION_ABORT": "1",
        "VK_LOADER_LAYERS_DISABLE": "~implicit~",
        "VK_DRIVER_FILES": "/usr/share/vulkan/icd.d/radeon_icd.json",
        "__EGL_VENDOR_LIBRARY_FILENAMES": "/usr/share/glvnd/egl_vendor.d/50_mesa.json",
        "VK_LAYER_PATH": str(runtime / "validation/prefix/usr/share/vulkan/explicit_layer.d"),
        "VK_INSTANCE_LAYERS": "VK_LAYER_KHRONOS_validation",
        "VK_LAYER_SETTINGS_PATH": str(runtime / "validation/vk_layer_settings.txt"),
        "VK_LAYER_VALIDATE_SYNC": "true",
        "VK_LOADER_DEBUG": "layer",
    },
    headless=True,
)
PYSESSION
```

The helper writes the owned session state to `session.json`, confines any nested
GUI to workspace 5 without changing focus, and creates `HEADLESS-2` for this older
runtime. Before loading the plugin, run the native validation prerequisite:

```sh
python3 "$recipe_dir/verify-native.py" --project "$PWD" \
    --session "$runtime_root/session.json" --output "$runtime_root/native-baseline" \
    --positive-control "$recipe_dir/baseline/validation-positive-control.txt"
```

This verifies loaded validation layers, the default SDR color contract, three
reloads and 20 native fullscreen toggles with 13 real captures. Any validation
error fails the check. Keep the session for the plugin tests only after this gate
passes; stop its recorded owned session with the project helper when finished.

Do not source that configuration in the daily compositor. The strict headless override omits both Wayland and physical DRM backends.
`AQ_BACKEND` alone is ignored by this older compositor and does not guarantee
headless isolation. Its `HEADLESS-1` name is reserved for the unsafe fallback:
create `HEADLESS-2` through the owned IPC
(`hyprctl -i "$owned_signature" output create headless HEADLESS-2`).
The AMD override validates an AMD PCI DRM render node and never acquires DRM
master, a seat session, or a physical output. Select the test machine's AMD
render-node path explicitly; the node number is machine-specific.

Require the owned log to name `AMD Radeon RX Vega (RADV VEGA10)` and report
`Found matching Vulkan physical device`. Capture actual frames and assert the
plugin's behavior. `vulkaninfo`, a client using Vulkan under OpenGL, compiling a
plugin, or a clean load rejection does not prove Hyprflow Vulkan rendering.

The final runtime reports its modified source state. The explicit patches and
artifact hashes identify the qualified build; a base commit alone does not.

Qualification begins with a plugin-free native fixture, nonempty screenshot,
configuration error check and three reloads. Only load Hyprflow after this
baseline succeeds. Initial upstream failures and their cores remain local; do
not attribute those plugin-free crashes to Hyprflow or to a reporter's photo.

Known native limitations remain: this is experimental upstream WIP, with ICC,
HDR/FP16, hardware cursors and client explicit-sync qualification incomplete.
Inner-glow drawing and global blend toggling contain unimplemented paths. The
shadow wrapper preserves the existing no-window-cutout behavior because its
native push data has no cutout geometry. The native baseline qualifies only normal-orientation SDR headless Vulkan on
the selected AMD device; do not infer other GPUs, rotated outputs or physical
HDR display correctness from it.

Rotated Vulkan output is a failed native control, independently of Hyprflow.
At transform 1 after the scale sequence 1, 1.25, 1.5, 2, a native terminal
fullscreen/restore round trip had mean absolute image delta 0.26436574074074076.
Its screenshot also showed sideways content in the first 900 rows and a black
remaining 540 rows of the 900x1440 output. The attempted clear-damage transform
change did not fix that native control and was reverted. It is absent from the
successful runtime patch, and no endpoint threshold was relaxed.
See `baseline/native-rotation/summary-public.json` for the failed control;
`baseline/native-core-sync-historical/summary-public.json` records the earlier
pre-v1 normal-orientation, default-EOTF baseline with core/sync validation,
three reloads, 20 fullscreen toggles and 13 actual captures. The rotated control was
not rerun after the latest native color and synchronization fixes and remains
outside the qualified scope.

The REPL backport passed 73 live checks for string/boolean/nil and multiple
returns, expression fallback, eval compatibility, syntax/runtime errors, timeout
recovery and protected `__tostring` conversion. See `baseline/repl-manifest.json`.
Those historical REPL checks bind to the earlier executable. The REPL component
source hunks remain byte-identical in the current runtime; final component
regressions inspect Lua status through the same REPL backport. Do not call the historical
73-check run a fresh run of the newer rendering/synchronization executable.

An optional standalone shader check is included. It compiles ten valid native
shadow feature combinations using the already-installed glslang validator:

```sh
python3 "$recipe_dir/check-shadow-shaders.py" \
    --source "$runtime_root/hyprland/src/render/shaders/glsl" \
    --output "$runtime_root/shadow-shader-proof"
```

This shader check does not replace native rendering or plugin runtime tests.

The default SDR export defect was fixed in the native renderer, not compensated
inside Hyprflow's shader: framebuffer image descriptions now take priority, so
an sRGB screenshot target is not misinterpreted as Gamma22. Native stencil
allocation queries format support and falls back from D24S8 to D32S8 on Vega.
Current native dynamic passes attach no depth/stencil image, so their pipeline
stencil/depth format declarations correctly remain undefined. Timeline signals
cover ALL_COMMANDS, with explicit previous-completion to staging to rendering
waits. These native repairs are included in `qualification.patch`.

## Final native resource and cleanup repairs

The final patch always allocates and binds an immutable gradient UBO for every
native border draw, including the config-error overlay whose border has no
window. It uses the selected feature pipeline's descriptor layout, and the
command buffer retains each UBO until completed GPU work permits reuse. This
replaces the unsafe per-window cache and avoids stale descriptor bindings.
Native border push-data sizing and upload always include the geometry block,
including sharp, color-managed borders.

Shutdown waits for outstanding GPU work before releasing monitor, error-overlay,
and pointer resources. Command buffers, descriptor pools, images and the device
are destroyed before their parent instance. These changes are part of the
qualification ABI v1 patch, not system compositor modifications.

Earlier native screenshots, 13-check synchronization baselines and 73-check REPL
results in `baseline/native-core-sync-historical/` and `baseline/repl-manifest.json`
are explicitly historical and retain their original binary identities. Final
v1 component regression and output-guard receipts are stored separately. The
full final Hyprflow test suite is reported by the project qualification report;
this dependency preparation package does not silently relabel earlier runs as
fresh final-v1 tests.

Final v1 component receipts included here are
`baseline/pre-blur-component-regression.json` (same-base old-plugin rejection,
rendering/selection and native windowless error-overlay regression) and
`baseline/output-guard-proof.json` (the final product's protective unsupported
output handling). Their artifact identities are separate from historical
native captures. The port agent's final native-only teardown/ABI probe package
and the project's final full-suite report provide the remaining final-run
receipts; do not substitute the historical files for those results.

## Final native blur and output-reconfiguration delta

The intermediate 1e1 graphics executable includes cpp-only native repairs after
the a921 v1 component tests. BlurPass has its own attachment LOAD path: its begin/end
barriers now pair color-attachment read/write operations with subsequent
fragment-shader reads, and the blur caller uses matching input and restoration
memory scopes. Monitor mode/format/size changes wait for outstanding Vulkan
work before replacing old resources; this is a reconfiguration boundary, not a
per-frame device wait.

No headers, class layouts or API hash changed in this delta, so the SDK retains
qualification ABI v1. That graphics executable is identified by SHA-256
`1e1ffac2f71cbba2180fffc3ca3701087cb359c24e5313e5dc0a17677d9fe30d`.
`baseline/final-native-fraction-blur.json` records its native-only transparent
blur control before plugin loading: actual 1440x900 mode, scale sequence
1→1.25→1.5→2→1, normal transform, 8-bit SDR, 0.8 client opacity, workspace
switches, working REPL and zero core/synchronization validation errors.
Earlier native ErrorOverlay/sharp-border/cleanup component receipts retain their
per-control executable hashes in `baseline/native-component-history.json`.
They are not relabeled as fresh results for the latest executable. The final
product's full test report remains the authoritative full-suite record.

## Final native keybinding snapshot delta

The intermediate keybinding executable is identified by SHA-256
`02e496f284517c0b64bedb18cd1d49db9fa6e7c33a3e4a923303eacf03f76a6c`.
The only change after the 1e1 graphics/blur executable is the KeybindManager.cpp
filter condition, backported from release 0.56.2 to compare the existing
`key.submapAtPress.name`. It does not change headers, class layouts, rendering
code or qualification ABI v1.

The native Lua-only counter control showed the old defect: a callback changing
submaps made one key press run the new submap's matching binding and skip a
second binding in the original submap (counters 1,0,1). After the filter repair,
the same press runs both original bindings and none from the newly entered
submap (1,1,0). Key release/modifier clearing does not change those counters.
`baseline/final-native-keybind.json` records this control and the unchanged
12-case release-selection suite passing with zero validation errors.

Graphics component receipts explicitly retain their 1e1 executable identity;
the graphics sources are unchanged by this final input-only delta. The full
final product/raw-input/lifecycle and exit results remain separate project
qualification receipts. Use this FINAL package's native and patch hashes rather
than an earlier intermediate bundle.

## Final native focus restoration delta

The authoritative final executable is identified by SHA-256
`6a4e23cedc63c7f9d76336a67cce1f4b3f178170e916e37906988f42963f3922`.
The only source change after 02e is the release-0.56.2 FocusState.cpp condition
that permits same-window focus restoration when its keyboard surface has been
cleared. The native control changed from desktop/seat surface focus both false
to both true. The unchanged persistent-keyboard raw-input proof then passed
modal key isolation and post-Return/Escape focus restoration with zero validation
errors. See `baseline/final-native-focus-input.json`.

No headers, fields, rendering code or qualification ABI changed in this final
input correction. Earlier graphics and keybinding component receipts keep
their actual executable hashes; the final full-suite/lifecycle/exit report is
recorded separately by the project qualification run.

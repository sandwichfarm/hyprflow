---
name: hyprflow-config-proof
description: Verify Hyprflow config and Lua controls in owned sessions, covering applied appearance, reloads, input cleanup, and renderer evidence.
---

# Prove configuration behavior

Choose assertions for the behavior being changed. Reuse the existing proof helpers;
do not substitute a `getoption` lookup for the rendered or input behavior under test.
Run from the repository root in an isolated worktree.

## Own the session and artifact

Build against headers matching the compositor to be tested. Unload an already-loaded
library before rebuilding it. Record the plugin hash and runtime version; the plugin's
ABI guard intentionally rejects mismatched headers. The experimental Vulkan path is
compiled separately with `VULKAN=1 BUILD_DIR=build-vulkan` against its pinned WIP
compositor headers; a stable OpenGL artifact is not a Vulkan artifact. Keep the
matching compositor revision, headers, plugin build, and selected GPU in the receipt.

For the ordinary nested Wayland path:

```sh
make check format-check
artifact="$PWD/build/hyprflow.so"
artifact_sha=$(sha256sum "$artifact" | cut -d' ' -f1)
session_dir=$(python3 scripts/nested-session.py start | python3 -c 'import json,sys; print(json.load(sys.stdin)["directory"])')
trap 'python3 scripts/nested-session.py stop "$session_dir"' EXIT
python3 scripts/nested-session.py place "$session_dir"
python3 scripts/nested-session.py fixtures "$session_dir" --calibration
python3 scripts/nested-session.py ctl "$session_dir" plugin load "$artifact"
```

Use this session identity for every IPC call. The helper launches visible test windows
directly on host workspace 5 with a silent, no-focus process-scoped rule. Keep them unpinned;
never switch the user's active host workspace to make a proof render. For background
proofs use `start --headless`; its startup config disables the parent Wayland output
before mapping and creates `HEADLESS-2` after IPC becomes available.
Hyprland's exec placement rules expire after one minute. Initial-window confinement
is not proof that an additional Wayland output will map safely later. Use headless
outputs for automated multi-output cases; do not create extra parent GUI windows
or rely on an expired exec rule. Do not add a global `aquamarine` class rule.
`place` and `stop` may place/restore only the exact owned window within workspace 5.
Do not load the plugin or change output settings in the daily compositor. Keep private logs and temporary evidence under a task-specific
`/tmp` directory; inspect and sanitize before publishing receipts.

## Pick the affected proof

- `verify-render-matrix.py`: effective scale/transform/color configuration, capture
  rendering and native accept/cancel endpoints, live output reconfiguration, cross-output
  exclusion/removal, and unload cycles. Inspect its effective-state checks before extending a matrix.
- `verify-plugin-rejection.py`: repeated incompatible-plugin load attempts with an expected
  diagnostic, unchanged plugin registry, and surviving compositor. Pass `--reason` when
  checking a renderer rejection instead of its default ABI mismatch.
- `verify-appearance.py`: current workspace aspect, overlay origin, tint, blur, reflections,
  captions, placement, borders, invalid settings, and reload behavior. Start with calibration
  fixtures; the proof replaces those fixtures for detailed scenes.
- `verify-select-on-release.py`: held chords, explicit exit, default-off behavior, and armed unload.
- `verify-input.py`: raw-client input isolation and focus restoration.
- `verify-lifecycle.py`: reversals, reloads, submap/focus restoration, and repeated plugin unload/load.
- `verify-configuration.py`: historical baseline/candidate border comparison. Read its phase
  requirements first; its old square-default assertion is not a current native-aspect oracle.

Read each script's `--help` before composing a run. Examples for current proofs:

```sh
python3 scripts/verify-render-matrix.py "$session_dir" /tmp/hyprflow-proof/matrix \
    --artifact "$artifact" --sha256 "$artifact_sha"
python3 scripts/verify-appearance.py "$session_dir" /tmp/hyprflow-proof/appearance \
    --artifact "$artifact" --sha256 "$artifact_sha"
python3 scripts/verify-select-on-release.py "$session_dir" --artifact "$artifact"
python3 scripts/verify-input.py "$session_dir" /tmp/hyprflow-proof/input
python3 scripts/verify-lifecycle.py "$session_dir" /tmp/hyprflow-proof/lifecycle \
    --artifact "$artifact" --sha256 "$artifact_sha"
```

For rejection proof, start a separate owned session without Hyprflow and supply
the incompatible artifact's actual hash:

```sh
python3 scripts/verify-plugin-rejection.py "$session_dir" "$artifact" --sha256 "$artifact_sha"
```

Use `isolated_input` from `nested-session.py` in new automated key proofs. It excludes
parent modifier contamination only inside the owned compositor and restores the device/config.
Restore temporary config in `finally`, including when cancellation or IPC fails.

## Assertions that matter

For changed settings, verify both Lua runtime assignment and file reload when applicable.
Check the observable result, rejection diagnostics, retained last-valid appearance, and
recovery to valid input. For bindings, use actual virtual-keyboard events and verify the
selected and activated workspace, cancel behavior, previous submap, and client focus.
Prove that a relevant broken behavior fails the new assertion when economical.

For scale, transform, GPU, HDR, or renderer cases, record the effective compositor state,
not just the requested configuration or environment. A rejected Vulkan plugin load proves
a safe rejection, not Vulkan rendering. An HDR request that remains SDR proves no HDR path.
Keep tests against other compositor ABIs separate from current-ABI runtime qualification.

Before reporting success, read the proof's completed receipt and verify artifact identity,
empty unexpected config errors, and cleanup. Stop owned sessions, restore temporary state,
and distinguish passing cases, expected rejection, unavailable hardware, and untested cases.

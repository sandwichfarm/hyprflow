# Hyprflow verification

## Hyprpm installation

Verified October 9, 2026, on Hyprland 0.56.2 in an isolated Arch Linux guest
with a VirGL OpenGL display, hosted through OrbStack. The
[installation receipt](../artifacts/hyprpm/verification.json) records the tested
commit, managed library hash, environment, commands, and results.

Hyprpm prepared matching headers, downloaded and built the plugin from the PR
branch, and enabled and loaded its managed library. Actual keyboard events
verified Super+Tab, both arrows, numeric selection, acceptance, and cancellation.
Restarting the compositor loaded the enabled plugin through the documented Lua
startup callback. The full example config passed both unloaded and loaded;
managed disable/reload and the modal catchall also passed without config errors.

This tests installation and controls, not performance under emulation. The PR
branch revision was supplied to `hyprpm add` because the default branch did not
yet contain the manifest. The first header setup exhausted the guest's small
runtime tmpfs; moving hyprpm's temporary workspace onto the guest disk allowed
the standard commands to complete.

## Original rendering qualification

Verified October 6, 2026, in an owned nested Hyprland session. The plugin,
animation specification, default configuration, screenshots, recordings, and
README are present. The daily compositor’s configuration and plugin list were
not modified. The nested compositor was stopped after testing.

## Exact target

- Hyprland 0.56.2, commit `efb50993780079460b0cbed1363e2166a2de1d9f`.
- OpenGL renderer; nested Wayland output, scale 1, normal orientation.
- Tested output sizes: 1280 × 720 and 960 × 960.
- Compiler: GCC 16.2.1, C++23.
- Plugin: `build/hyprflow.so`.
- SHA-256: `7a14a088eb4ffa7629995cc432117eba4c57d727b8c3ba861adfaac653795332`.

The navigation, stress, and lifecycle receipts verify the loaded library’s inode
and hash. [Build identity](../artifacts/final/build.json) and
[final runtime state](../artifacts/final/runtime.json) preserve that boundary.

## Requirement evidence

| Requirement | Evidence | Result |
| --- | --- | --- |
| Design before implementation | [Specification](design-spec.md), written before source implementation, with original iTunes screenshots and motion references | Complete |
| Faithful perspective, overlap, lighting, reflection | [Calibration](../artifacts/final/calibration.png), [visual verdict](../artifacts/final/visual-verdict.json) | 95/100, pass |
| Real workspace imagery | [Settled workspace flow](../artifacts/final/navigation/02-open.png) plus seven native fixture captures | Complete |
| Smooth entry and exit | [Navigation video](../artifacts/final/navigation/navigation.mp4), [motion contact sheet](../artifacts/final/motion-contact.jpg) | No observed plugin flash or teleport at inspected samples |
| Assignable left/right keys | [Navigation receipt](../artifacts/final/navigation/manifest.json), actual Wayland virtual-keyboard events | Both directions pass |
| Assignable workspace jumps | Same receipt: bound keys 1, 4, and 7 animate selection while the real workspace stays unchanged | Pass |
| Rapid retarget and reversal | [Stress video](../artifacts/final/stress/stress.mp4), [stress receipt](../artifacts/final/stress/manifest.json) | 15 actions; position preserved at retarget, monotonic stable exits |
| Activate, cancel, bounds, empty targets, errors | [Lifecycle receipt](../artifacts/lifecycle/manifest.json) | 20 checks pass |
| Modal keyboard isolation and focus restoration | [Raw-client input receipt](../artifacts/final/input/input-manifest.json) | No unbound/exit-key leakage; input returns after exit |
| Unload/reload safety | Lifecycle receipt: ten cycles, five unloaded while open | No crash; focus and submap restored after every unload |
| Default configuration | [hyprflow.lua](../config/hyprflow.lua), [fresh-session receipt](../artifacts/final/default-config.json) | Current file sourced; six repeatable arrow bindings, nine direct jumps, and catchall verified |
| README through readme-wizard | [README](../README.md), repository metadata scan, best-practices/template adaptation, local link checks | Complete |
| Isolated development and cleanup | [Cleanup receipt](../artifacts/final/cleanup.json) | Owned PID 851087 exited; daily Hyprflow not loaded |

## Measured visuals

The final square calibration has a selected-card aspect ratio of **1.000**.
The nearest visible side-card width is **0.555H**; its outer and visible inner
edge heights are **1.005H** and **0.753H**. These satisfy the source-backed
tolerances in the specification. Reflections start immediately below the card,
with measured contact opacity **0.340** and a smooth fade. Side lighting is
brighter toward the outer edge. Label placement follows card size.

Both `09-accepted.png` and `12-cancelled.png` are pixel-identical to the matching
native `fixture-7.png`: RGB mean absolute difference is zero. This establishes
the final handoff for the static fixture. It does not assert that arbitrary live
applications stop changing between frames.

The navigation and stress recordings are 1280 × 720 at nominal 60 fps, lasting
8.033333 s and 6.566667 s. FFprobe decoded 482 and 394 frames respectively; the
container metadata reports one additional frame in each recording. All decoded
frames were checked for blackouts. Visual motion review sampled every 50 ms,
including entry, commit, cancel, and rapid reversals. The navigation recording’s
initial native workspace 7-to-4 cut is fixture setup before F10 opens the plugin.

## Checks and simplifications

- `make check format-check`: native build, motion tests, Python syntax,
  Cppcheck warnings/performance/portability checks, and ClangFormat pass.
- ASan/UBSan motion tests pass. Tests include 12,001 geometry samples, measured
  landmarks, frame-rate independence, velocity-preserving reversal, and projective
  entry interpolation. A reversed-yaw mutation fails as expected. The projective
  interpolation test failed before its repair and passes afterward.
- Event-bus render passes replace the need for binary function hooks. The plugin
  uses one continuous focus coordinate and one opening coordinate for every
  navigation action. Workspace capture restores temporary scene state through
  RAII; no per-workspace switching is used to obtain snapshots.
- Visible-card caching bounds retained GPU textures. There are no downloaded or
  vendored runtime dependencies, background services, or daily-session changes.

## Limits and retained attempts

Apple’s exact proprietary timing constants are unknown. This is a measured
reconstruction against the documented iTunes references, with desktop-specific
entry/exit and aspect-preserving workspace containment. Widescreen snapshots
have black matte padding inside square covers.

Other Hyprland revisions, Vulkan, HDR, rotated/fractionally scaled outputs,
physical multi-monitor configurations, and interaction with other plugins were
not qualified. The tests establish the exact nested target above, not universal
desktop compatibility. The pure motion model was sanitizer checked; the whole
compositor was not rebuilt with sanitizers.

Earlier attempts remain under `artifacts/proof-iteration*`,
`artifacts/input-iteration*`, and the lifecycle archive. The failed final
recording under `artifacts/final/navigation-failed-super-modifier/` is retained
with its failure note. It was caused by a held Super modifier on the nested
parent keyboard. Automated proofs now temporarily isolate that nested device
and restore its configuration afterward. A separate earlier frame-starvation
incident came from the owned nested window being unpinned and moved off the
visible host workspace; the source of those placement changes was not proven.

## Files added

- `src/`: plugin entry points, flow controller, projective GL renderer, safe
  workspace capture, and pure motion math.
- `tests/motion.cpp`, `Makefile`, `.clang-format`, `.gitignore`.
- `config/hyprflow.lua`, `config/nested.lua`.
- `scripts/`: isolated session management, fixtures, input injection, capture,
  stress, input-isolation, and lifecycle verification tools.
- `docs/`, `README.md`, and `artifacts/`: specification, reference provenance,
  usage, evidence, and retained attempts.

The starting directory had no Git repository. No commits, remote repository,
release publication, package installation, or production plugin load were made.

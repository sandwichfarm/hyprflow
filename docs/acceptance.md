# Hyprflow acceptance gates

The requested result is a native Hyprland workspace navigation plugin with the
visual language and motion of classic iTunes Cover Flow. A build alone does not
complete this project.

1. Write the animation design specification before implementing the effect.
   Record reference provenance, geometry, movement, entry, exit, and fidelity limits.
2. Render actual workspace contents in a centered, front-facing card and overlapping
   perspective stacks with darkening and floor reflections.
3. Preserve visible position and velocity when navigation changes direction or a
   distant workspace becomes the target. Entry shrinks the current desktop into
   its card. Exit expands the chosen card into the desktop without a second native
   workspace slide.
4. Expose bindable left, right, and workspace-ID jump actions, plus open/toggle,
   accept, and cancel. Jump selection stays in the flow until accepted.
5. Develop and verify only in owned nested sessions. Every control command must
   address the nested session explicitly. Do not modify the daily configuration
   or load the development binary into the daily compositor.
6. Verify exact installed ABI, build, geometry/motion tests, invalid actions,
   selection versus activation, boundaries, cancel, rapid input, and load/unload
   lifecycle. Test the actual Lua key bindings using virtual keyboard input.
7. Generate actual compositor screenshots and a transition recording with an
   artifact hash and reproducible capture commands. Inspect the screenshots
   against historical references and persist visual verdicts.
8. Supply a working default configuration and a README using readme-wizard.
   Document tested compatibility and limitations without claiming broader proof.

9. Use each workspace's native aspect ratio, including portrait and ultrawide
   cases, without arbitrary square matte padding. Expose desktop overlay,
   background color/opacity/blur, reflections, captions, and vertical placement
   alongside size, spacing, and borders. Verify live changes and invalid values,
   update documentation, and show multiple configurations in the demo video.

Completion requires fresh evidence for every gate. Keep incomplete gates explicit.

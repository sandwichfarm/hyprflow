# Hyprflow animation specification

Status: implementation contract, 2026-10-06. Target: the desktop iTunes 7–10 Cover Flow visual language, with iTunes 7 and 7.1 screenshots as the reproducible reference set.

## Evidence and fidelity boundary

Apple introduced Cover Flow in iTunes 7 on September 12, 2006. Its [release announcement](https://www.apple.com/ca/newsroom/2006/09/12Apple-Announces-iTunes-7-with-Amazing-New-Features/) establishes the product and date. The visual specification below comes from inspection of original application captures, not another developer’s carousel implementation.

- [Jeremey Barrett’s September 12, 2006 capture](https://www.flickr.com/photos/jeremey/242170677/): [local 1024 × 683 image](reference/itunes-7-windowed-flickr.jpg). Primary geometry reference.
- [Apple Gazette’s iTunes 7.1 captures](https://www.applegazette.com/itunes/first-impressions-of-itunes-71-w-screenshots/): [full-screen](reference/itunes-7.1-fullscreen.jpg) and [windowed](reference/itunes-7.1-windowed.jpg). Their image metadata is dated March 5, 2007; the current article displays a later republishing date.
- [bluemint’s April 9, 2007 iTunes screen recording](https://www.youtube.com/watch?v=1nCeJWxp4yk): motion reference. The first 20 seconds show a stationary selection followed by fast travel through a dense album collection. It supports continuous movement and overlapping rotation, but does not expose the input events or Apple’s easing constants. A [twelve-frame excerpt](reference/itunes-motion-samples.jpg) records the first transitions.

File origins, hashes, dates, and extraction details are recorded in [reference provenance](reference/SOURCES.md).

These references establish appearance, overlap, perspective direction, reflections, and the continuous relationship between position and rotation. They do not reveal Apple’s source code, camera parameters, or exact timing. Numerical values below are Hyprflow reconstruction targets. Perfect equivalence to every iTunes version is not established. Workspace entry and exit are an explicit adaptation: iTunes did not animate a Hyprland desktop into an album cover.

## Measured visual targets

Coordinates below use the unmodified 1024 × 683 Flickr image, origin at its upper-left. Measurements are approximate; compression and partial occlusion limit precision.

| Landmark | Measured pixels | Normalized observation |
| --- | --- | --- |
| Center card | x 482–733, y 105–356 | Square; side length 251 px |
| Center card horizontal midpoint | x 607.5 | Matches the 237–978 px flow viewport midpoint |
| Nearest left card outer edge | x ≈339, y ≈115–375 | Height ≈1.04 center-card heights |
| Nearest left card visible inner edge | x ≈482, y ≈155–338 | Height ≈0.73 center-card heights; partially occluded |
| Nearest left card visible width | ≈143 px | ≈0.57 center-card widths |
| Successive left outer edges | x ≈339, 294, 271 | Dense overlap; several receding faces remain identifiable |
| Center reflection contact | y ≈356 | No detached gap between card and reflection |
| Center reflection | visible beneath the title and scrollbar | Vertical mirror; fades into black |

The 420 × 263 full-screen reference has a roughly 162 px center card, or 0.616 of viewport height. Its selected card is slightly right of screen center, so it is a composition reference rather than an exact centering target. The nearest left card again has a taller outer edge and a shorter inner edge.

Acceptance targets for a settled Hyprflow frame:

1. The selected square is front-facing, sharp, opaque, and visually dominant.
2. Both side stacks have vertical edges. Their **outer edges are taller and closer** than their inner edges. Left and right stacks mirror each other.
3. The nearest side cover is mostly visible; farther covers overlap densely rather than occupying separate thumbnail tiles.
4. Reflections touch the respective lower edges and preserve each card’s perspective.
5. The stage is black. No rounded corners, colored glow, frosted panel, thick outline, or elliptical carousel path is introduced.

## Coordinate and projection contract

Let `H` be the square card side length. All world distances below are multiples of `H`. World x increases right, y increases down, and positive z points toward the viewer. The camera is centered on the row and looks down negative z.

Default composition:

- `H = min(0.58 × monitor_height, 0.38 × monitor_width)`.
- Selected card center: `(0.50 × monitor_width, 0.40 × monitor_height)`.
- Camera distance / focal length: `F = 2.5H`.
- Maximum yaw magnitude: `65°`.
- First side-card world center: `0.84H` from the selected center.
- Subsequent side-card center spacing: `0.18H`.
- Side-card center depth: `−0.45H`.
- Card pitch and roll: `0°`.

For a settled side card, left yaw is `+65°`, right yaw is `−65°`. For a local card point `(u, v, 0)`, where both `u` and `v` range from `−H/2` to `+H/2`:

```text
world_x = center_x + u × cos(yaw)
world_y = v
world_z = center_z − u × sin(yaw)
projected_x = stage_center_x + F × world_x / (F − world_z)
projected_y = stage_center_y + F × world_y / (F − world_z)
```

This sign convention makes the outside edge of each side stack closer. With the defaults, a side card’s outer edge is about `1.001H` tall and its inner edge about `0.735H` tall. Its visible width next to the selected cover is about `0.55H`, after central occlusion. These are close to the measured `1.04H`, `0.73H`, and `0.57H` reference landmarks.

Perspective must remain projective throughout the textured quad. Two affine triangles with no perspective correction create a diagonal kink and do not meet the target. Depth ordering must consistently put nearer cards above farther cards; the centered card is foremost at rest. Equal-distance ties use a stable order.

## Continuous flow geometry

Maintain a continuous focus coordinate `q`; workspace at row index `i` has signed distance `d = i − q`. Never calculate pose from only the nearest integer selection. Every intermediate position must exist.

For `a = abs(d)`, the center-to-side transition must be continuous in position and yaw. Use an odd horizontal function and odd yaw function. A suitable interpolation uses cubic Hermite from center to side:

```text
for 0 ≤ a ≤ 1:
    s(a) = a² × (3 − 2a)
    yaw(d) = −sign(d) × 65° × s(a)
    depth(d) = −0.45H × s(a)
    x(d) = sign(d) × H × hermite(a; start=0, end=0.84,
                                        start_slope=1.5, end_slope=0.18)
for a > 1:
    yaw(d) = −sign(d) × 65°
    depth(d) = −0.45H
    x(d) = sign(d) × H × (0.84 + 0.18 × (a − 1))
```

The endpoint derivative matches the stack spacing. The center derivative carries cards smoothly across the focal region. Use the same function for left/right moves, repeats, and direct jumps. A jump changes the destination focus coordinate; it does not replace the visible row or crossfade between unrelated selections. Workspace order stays stable throughout one open session.

## Motion contract

Movement should resemble a heavy, controlled stack sliding through a focal position. Avoid elastic bounce, overshoot, per-card stagger, and abrupt orientation flips.

A critically damped, frame-rate-independent spring is the initial timing target for `q`. Start with natural frequency `20 s⁻¹`. A one-card step reaches 90% in about 195 ms and 99% in about 332 ms. These values are reconstruction choices, not measurements of Apple’s implementation.

Preserve both position and velocity when a target changes. A left/right reversal or new jump must not restart from rest. Evaluate elapsed monotonic time, not a fixed increment per frame. Snap to the destination only after both position and speed are below visually negligible tolerances; the resulting projected displacement must stay below one output pixel.

Large jumps follow the same path and show intermediate cards. Repeated key presses update the target without waiting for earlier animations. Clamp at row ends. Do not wrap from the last card to the first unless a separate wrapping mode is explicitly designed.

## Workspace imagery and lighting

Each cover contains a snapshot of the complete workspace. Preserve its aspect ratio with containment inside the square, using black matte padding. Never stretch a widescreen desktop to square. Empty workspaces still have a stable cover and identity. The backdrop, windows, and decorations must refer to the same workspace capture.

The selected cover uses the snapshot’s original brightness. Side covers are moderately shaded as yaw increases, with a subtle horizontal gradient; the outer edge remains legible. Initial target: center multiplier `1.0`, side multiplier approximately `0.72–0.82`. Do not use stronger dimming to conceal incorrect geometry.

Reflection geometry mirrors the transformed card across its lower world edge, rather than mirroring its screen bounding box. Reflect the complete cover, including matte padding. Initial reflection opacity at contact is `0.34`; fade smoothly to zero over about `0.45H`. No hard bottom cutoff or duplicate title in the reflection. Reflections remain behind all upright cards.

A small, centered workspace number/name may sit below the selected cover. It must not obstruct the image or become a large product heading. Labels update to the target only when the corresponding cover reaches the focal region, avoiding a new name on an old cover.

## Entry and exit

Entry and exit are first-class animations. A fade to a prearranged carousel does not satisfy this contract.

### Entry

1. Capture the current workspace at its exact monitor geometry before taking visual ownership.
2. The first presented plugin frame reproduces that workspace at full-monitor size, with no visible seam, duplicate image, or black flash.
3. Continuously transform the same snapshot into the selected cover’s contained image. Preserve source aspect ratio throughout. Reveal the square matte as the cover contracts.
4. Fade the black stage and side stack in during that contraction. Reflection opacity follows the entry progress and is zero at the first frame.
5. Arrive at the settled composition with negligible velocity. Initial target: roughly 350–450 ms.

### Exit and commit

1. If selection is still moving, complete the focus movement before expanding the chosen cover. Avoid an unannounced sideways teleport.
2. Expand the selected workspace image from its contained cover rectangle to the exact monitor rectangle. Fade matte padding, side cards, reflection, and labels continuously.
3. Switch the compositor’s real workspace underneath the covering image before the final reveal. Do not expose Hyprland’s ordinary workspace slide simultaneously.
4. Remove visual ownership only when the overlay’s final image and destination workspace match. The next compositor frame must not flash black or show the previous workspace.

### Cancel and interruption

Cancel returns to the workspace active when entry began. A second toggle during entry reverses from the current visible pose. It must not recreate the overlay from its fully open state. Navigation and opening progress are independent continuous states. Reversing either preserves its current value and velocity.

Never mutate normal monitor arrangement or daily-session configuration to demonstrate this behavior. Development and proof use a separate nested Wayland compositor.

## Input behavior

Expose independently bindable actions for opening/toggling, moving left, moving right, jumping to a workspace, committing, and canceling. Left/right actions move the flow selection; a jump selects the target through continuous flow travel. Document whether a navigation action implicitly opens the flow. Invalid targets must return an explicit failure without changing the current selection.

## Proof and acceptance

Build success alone does not prove fidelity. Retain the actual nested-session outputs and identify the compositor build and plugin artifact used.

- Capture settled center and both side stacks with at least five recognizable workspace snapshots.
- Compare the silhouette against the local reference images, checking yaw direction, outer/inner height ratio, overlap, reflection contact, black stage, and absence of extra visual ornament.
- On the square calibration case, require selected aspect ratio `1.00 ± 0.01`, outer-edge height `1.00 ± 0.08H`, inner-edge height `0.735 ± 0.06H`, and nearest visible width `0.55 ± 0.08H`.
- Capture contiguous entry, one-step travel, rapid reversal, multi-workspace jump, commit, and cancel. Screenshots alone cannot prove smoothness; keep a recording or frame sequence.
- Inspect the first entry frame and final exit frame against the adjacent native desktop frames. Require no unrelated workspace, missing window, aspect distortion, or black flash.
- Exercise bound left/right and workspace-specific jump actions in the nested compositor. Verify the destination workspace via compositor state after commit, and original workspace after cancel.
- Report capture rate and frame timestamps. Inspect for geometry discontinuities, skipped pose states, and one-frame z-order pops. State any recording limitations instead of inferring perfect temporal fidelity from a still image.

The acceptance claim is faithful reconstruction against these documented references and measured targets. Exact proprietary constants and pixel equivalence to all iTunes builds remain unproven.

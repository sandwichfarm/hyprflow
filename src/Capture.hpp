#pragma once

#include <hyprland/src/desktop/DesktopTypes.hpp>
#include <hyprland/src/render/Framebuffer.hpp>

namespace Hyprflow {

/**
 * Capture one workspace before the monitor's normal render begins.
 * A null workspace produces an empty preview with wallpaper, layers, and pinned windows.
 * All temporary scene state is restored before returning. The caller owns the framebuffer.
 */
bool captureWorkspace(PHLMONITOR monitor, PHLWORKSPACE workspace, SP<Render::IFramebuffer> &framebuffer);

} // namespace Hyprflow

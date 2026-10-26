#pragma once

#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/desktop/Workspace.hpp>
#ifdef HYPRFLOW_VULKAN
#include <hyprland/src/Compositor.hpp>
#include <hyprland/src/helpers/Monitor.hpp>
#include <hyprland/src/managers/animation/DesktopAnimationManager.hpp>
#else
#include <hyprland/src/output/Monitor.hpp>
#include <hyprland/src/state/WorkspaceState.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/animation/WorkspaceAnimationController.hpp>
#endif

// The experimental Vulkan branch predates Hyprland's workspace/window state split.
namespace Hyprflow::Compat {
inline auto workspaceReferences() {
#ifdef HYPRFLOW_VULKAN
    return g_pCompositor->getWorkspaces();
#else
    return State::workspaceState()->workspaces();
#endif
}
inline auto workspaces() {
#ifdef HYPRFLOW_VULKAN
    return g_pCompositor->getWorkspacesCopy();
#else
    return State::workspaceState()->workspacesCopy();
#endif
}
inline decltype(auto) windows() {
#ifdef HYPRFLOW_VULKAN
    return (g_pCompositor->m_windows);
#else
    return Desktop::windowState()->windows();
#endif
}
inline auto &position(const PHLWINDOW &window) {
#ifdef HYPRFLOW_VULKAN
    return window->m_realPosition;
#else
    return window->positionAnimation();
#endif
}
inline auto &size(const PHLWINDOW &window) {
#ifdef HYPRFLOW_VULKAN
    return window->m_realSize;
#else
    return window->sizeAnimation();
#endif
}
inline auto &specialDim(const PHLMONITOR &monitor) {
#ifdef HYPRFLOW_VULKAN
    return monitor->m_specialFade;
#else
    return monitor->m_specialDim;
#endif
}
inline auto &specialBlur(const PHLMONITOR &monitor) {
#ifdef HYPRFLOW_VULKAN
    return monitor->m_specialFade;
#else
    return monitor->m_specialBlur;
#endif
}
inline auto create(WORKSPACEID id, MONITORID monitor, const std::string &name) {
#ifdef HYPRFLOW_VULKAN
    return g_pCompositor->createNewWorkspace(id, monitor, name);
#else
    return State::workspaceState()->create(id, monitor, name);
#endif
}
inline void stopWorkspaceAnimations(const PHLWORKSPACE &old, const PHLWORKSPACE &next) {
#ifdef HYPRFLOW_VULKAN
    g_pDesktopAnimationManager->startAnimation(old, CDesktopAnimationManager::ANIMATION_TYPE_OUT, true, true);
    g_pDesktopAnimationManager->startAnimation(next, CDesktopAnimationManager::ANIMATION_TYPE_IN, true, true);
#else
    Animation::Workspace::startAnimation(old, Animation::Workspace::ANIMATION_TYPE_OUT, true, true);
    Animation::Workspace::startAnimation(next, Animation::Workspace::ANIMATION_TYPE_IN, true, true);
#endif
}
} // namespace Hyprflow::Compat

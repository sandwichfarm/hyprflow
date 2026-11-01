#pragma once

// Source compatibility across the supported compositor revisions:
// - HYPRFLOW_VULKAN: the experimental Vulkan branch, which predates Hyprland's workspace/window state split.
// - Hyprland 0.56.x (the default OpenGL build).
// - Hyprland 0.57.x: relocated window/workspace headers, variant workspace IDs, per-frame renderer state
//   moved into a render context. Detected from the headers that hyprpm or pkg-config selected.
#if !defined(HYPRFLOW_VULKAN) && __has_include(<hyprland/src/workspace/HLWorkspace.hpp>)
#define HYPRFLOW_HYPRLAND_057 1
#else
#define HYPRFLOW_HYPRLAND_057 0
#endif

#include <hyprland/src/desktop/DesktopTypes.hpp>
#include <hyprland/src/managers/input/InputManager.hpp>
#include <hyprland/src/render/Renderer.hpp>
#if HYPRFLOW_HYPRLAND_057
#include <hyprland/src/animation/WorkspaceAnimationController.hpp>
#include <hyprland/src/config/shared/actions/ConfigActions.hpp>
#include <hyprland/src/debug/log/Logger.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/desktop/view/window/Window.hpp>
#include <hyprland/src/desktop/view/window/WindowPresentation.hpp>
#include <hyprland/src/output/Monitor.hpp>
#include <hyprland/src/pointer/PointerManager.hpp>
#include <hyprland/src/render/Context.hpp>
#include <hyprland/src/state/WorkspaceState.hpp>
#include <hyprland/src/workspace/HLWorkspace.hpp>
#else
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/desktop/Workspace.hpp>
#include <hyprland/src/managers/KeybindManager.hpp>
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
#endif

#include <cstdint>
#include <limits>
#include <optional>
#include <string>

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
inline int windowCount(const PHLWORKSPACE &workspace) {
#ifdef HYPRFLOW_VULKAN
    return workspace->getWindows();
#else
    return workspace->getWindowCount();
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
inline void stopWorkspaceAnimations(const PHLWORKSPACE &old, const PHLWORKSPACE &next) {
#ifdef HYPRFLOW_VULKAN
    g_pDesktopAnimationManager->startAnimation(old, CDesktopAnimationManager::ANIMATION_TYPE_OUT, true, true);
    g_pDesktopAnimationManager->startAnimation(next, CDesktopAnimationManager::ANIMATION_TYPE_IN, true, true);
#else
    Animation::Workspace::startAnimation(old, Animation::Workspace::ANIMATION_TYPE_OUT, true, true);
    Animation::Workspace::startAnimation(next, Animation::Workspace::ANIMATION_TYPE_IN, true, true);
#endif
}

// Numeric workspace identity used by the flow. Named workspaces have no number on any revision.
using WorkspaceNumber = int64_t;

inline std::optional<WorkspaceNumber> workspaceNumber(const PHLWORKSPACE &workspace) {
    if (!workspace)
        return std::nullopt;
#if HYPRFLOW_HYPRLAND_057
    const auto numbered = workspace->numberedID();
    if (!numbered)
        return std::nullopt;
    return static_cast<WorkspaceNumber>(*numbered);
#else
    if (workspace->m_id <= 0)
        return std::nullopt;
    return workspace->m_id;
#endif
}

// Hyprland 0.56 gives named workspaces stable negative IDs; 0.57 identifies them only by name.
inline std::optional<WorkspaceNumber> namedWorkspaceID(const PHLWORKSPACE &workspace) {
#if HYPRFLOW_HYPRLAND_057
    return std::nullopt;
#else
    if (!workspace || workspace->m_id == WORKSPACE_INVALID)
        return std::nullopt;
    return workspace->m_id;
#endif
}

inline std::string workspaceName(const PHLWORKSPACE &workspace) {
#if HYPRFLOW_HYPRLAND_057
    return workspace->displayName();
#else
    return workspace->m_name;
#endif
}

inline bool workspaceSpecial(const PHLWORKSPACE &workspace) {
#if HYPRFLOW_HYPRLAND_057
    return workspace->type() == Workspace::eWorkspaceType::SPECIAL;
#else
    return workspace->m_isSpecialWorkspace;
#endif
}

// A workspace the compositor has destroyed but which a card still references.
inline bool workspaceGone(const PHLWORKSPACE &workspace) {
#if HYPRFLOW_HYPRLAND_057
    for (const auto &live : State::workspaceState()->workspaces()) {
        if (live.lock() == workspace)
            return false;
    }
    return true;
#else
    return workspace->inert();
#endif
}

inline bool workspaceVisible(const PHLWORKSPACE &workspace) {
#if HYPRFLOW_HYPRLAND_057
    return workspace->visible();
#else
    return workspace->m_visible;
#endif
}

inline void setWorkspaceVisible(const PHLWORKSPACE &workspace, bool visible) {
#if HYPRFLOW_HYPRLAND_057
    workspace->setVisible(visible);
#else
    workspace->m_visible = visible;
#endif
}

inline PHLWORKSPACE create(WorkspaceNumber id, const PHLMONITOR &monitor, const std::string &name) {
#if HYPRFLOW_HYPRLAND_057
    if (id <= 0 || id > static_cast<WorkspaceNumber>(std::numeric_limits<Workspace::WorkspaceIDContainer>::max()))
        return nullptr;
    return State::workspaceState()->createNumbered(Workspace::SWorkspaceNumberedID{static_cast<Workspace::WorkspaceIDContainer>(id)}, monitor, name);
#elif defined(HYPRFLOW_VULKAN)
    return g_pCompositor->createNewWorkspace(id, monitor->m_id, name);
#else
    return State::workspaceState()->create(id, monitor->m_id, name);
#endif
}

// Hyprland 0.57 requires a newly created workspace to be marked ready after it has been placed.
inline void workspaceReady(const PHLWORKSPACE &workspace) {
#if HYPRFLOW_HYPRLAND_057
    if (workspace)
        workspace->ready();
#endif
}

inline bool windowPinned(const PHLWINDOW &window) {
#if HYPRFLOW_HYPRLAND_057
    return (window->m_state & Desktop::View::WINDOW_STATE_PINNED) != Desktop::View::WINDOW_STATE_NONE;
#else
    return window->m_pinned;
#endif
}

inline auto &windowAlpha(const PHLWINDOW &window, Desktop::View::eWindowAlpha type) {
#if HYPRFLOW_HYPRLAND_057
    return window->presentation().alpha(type);
#else
    return window->alpha(type);
#endif
}

#if HYPRFLOW_HYPRLAND_057
namespace Detail {
// Standard-conforming access to a private member: explicit instantiation may name private members.
template <typename Tag, typename Tag::type Member> struct Steal {
    friend typename Tag::type get(Tag) {
        return Member;
    }
};
struct FloatingOffsetTag {
    using type = Desktop::View::CFloatingOffset Desktop::View::CWindowPresentation::*;
    friend type get(FloatingOffsetTag);
};
template struct Steal<FloatingOffsetTag, &Desktop::View::CWindowPresentation::m_floatingOffset>;
struct MappedTag {
    using type = bool Desktop::View::CWindow::*;
    friend type get(MappedTag);
};
template struct Steal<MappedTag, &Desktop::View::CWindow::m_isMapped>;
} // namespace Detail

// Capture hides windows by clearing the mapped flag directly; setHidden would emit hide/show events.
inline bool &windowMapped(const PHLWINDOW &window) {
    return (*window).*get(Detail::MappedTag{});
}
// The floating offset carries its source; capture must restore both exactly.
using FloatingOffset = Desktop::View::CFloatingOffset;
inline FloatingOffset &windowFloatingOffset(const PHLWINDOW &window) {
    return window->presentation().*get(Detail::FloatingOffsetTag{});
}
inline void clearFloatingOffset(const PHLWINDOW &window) {
    window->presentation().clearFloatingOffset();
}
#else
inline bool &windowMapped(const PHLWINDOW &window) {
    return window->m_isMapped;
}
using FloatingOffset = Vector2D;
inline FloatingOffset &windowFloatingOffset(const PHLWINDOW &window) {
    return window->m_floatingOffset;
}
inline void clearFloatingOffset(const PHLWINDOW &window) {
    window->m_floatingOffset = {};
}
#endif

// The renderer's current pass. On 0.57 it lives in the renderer's single render context.
inline Render::CRenderPass &renderPass() {
#if HYPRFLOW_HYPRLAND_057
    return g_pHyprRenderer->context().m_pass;
#else
    return g_pHyprRenderer->m_renderPass;
#endif
}

inline std::string currentSubmap() {
#if HYPRFLOW_HYPRLAND_057
    return Config::Actions::state()->m_currentSubmap;
#else
    return g_pKeybindManager->getCurrentSubmap().name;
#endif
}

inline void setSubmap(const std::string &name) {
    const auto target = name.empty() ? "reset" : name;
#if HYPRFLOW_HYPRLAND_057
    if (const auto result = Config::Actions::setSubmap(target); !result)
        Log::logger->log(Log::ERR, "[hyprflow] {}", result.error().message);
#else
    g_pKeybindManager->m_dispatchers.at("submap")(target);
#endif
}

// Modifiers held on all keyboards, excluding the Caps Lock and Num Lock states.
inline uint32_t heldModifiers() {
#if HYPRFLOW_HYPRLAND_057
    return static_cast<uint32_t>(g_pInputManager->getModsFromAllKBs() & ~(Input::HL_MODIFIER_CAPS | Input::HL_MODIFIER_MOD2));
#else
    return g_pInputManager->getModsFromAllKBs() & ~(HL_MODIFIER_CAPS | HL_MODIFIER_MOD2);
#endif
}

// Keeps the monitor composited while the flow is visible. Direct scanout would bypass the overlay.
class ScanoutBlock {
  public:
    explicit ScanoutBlock(PHLMONITOR monitor) : m_monitor(monitor) {
#if HYPRFLOW_HYPRLAND_057
        // 0.57 removed the global block flag; a software-cursor lock is the supported per-monitor blocker.
        Pointer::mgr()->lockSoftwareForMonitor(monitor);
#else
        m_previous = g_pHyprRenderer->m_directScanoutBlocked;
        g_pHyprRenderer->m_directScanoutBlocked = true;
#endif
    }
    ~ScanoutBlock() {
#if HYPRFLOW_HYPRLAND_057
        if (const auto monitor = m_monitor.lock(); monitor && Pointer::mgr())
            Pointer::mgr()->unlockSoftwareForMonitor(monitor);
#else
        g_pHyprRenderer->m_directScanoutBlocked = m_previous;
#endif
    }
    ScanoutBlock(const ScanoutBlock &) = delete;
    ScanoutBlock &operator=(const ScanoutBlock &) = delete;

  private:
    PHLMONITORREF m_monitor;
#if !HYPRFLOW_HYPRLAND_057
    bool m_previous = false;
#endif
};
} // namespace Hyprflow::Compat

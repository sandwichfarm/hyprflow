#include "Capture.hpp"
#include "CompositorCompat.hpp"

#include <hyprland/src/helpers/time/Time.hpp>
#include <hyprland/src/render/OpenGL.hpp>
#include <hyprland/src/render/Renderer.hpp>
#if HYPRFLOW_HYPRLAND_057
#include <hyprland/src/render/pass/ClearPassElement.hpp>
#endif

#include <algorithm>
#include <exception>
#include <utility>
#include <vector>

namespace Hyprflow {
namespace {

// Expose the protected member pointer without changing Hyprland's headers or casting its renderer to a derived object.
struct RendererAccess : Render::IHyprRenderer {
#if !HYPRFLOW_HYPRLAND_057
    using IHyprRenderer::m_renderMode;
#endif
    using IHyprRenderer::renderWorkspace;
#ifdef HYPRFLOW_VULKAN
    using IHyprRenderer::setDamage;
#endif
};

#if !HYPRFLOW_HYPRLAND_057
constexpr auto RENDER_MODE = &RendererAccess::m_renderMode;
#endif
#ifdef HYPRFLOW_VULKAN
constexpr auto SET_DAMAGE = &RendererAccess::setDamage;
#endif

struct WorkspaceState {
    PHLWORKSPACE workspace;
    bool visible = false;
    bool forceRendering = false;
    float alpha = 1;
    Vector2D offset;
};

struct WindowState {
    PHLWINDOW window;
    bool mapped = false;
    Vector2D position;
    Vector2D size;
    Compat::FloatingOffset floatingOffset;
    float moveToAlpha = 1;
    float moveFromAlpha = 1;
};

class SceneState {
  public:
    explicit SceneState(PHLMONITOR monitor)
        : m_monitor(monitor), m_active(monitor->m_activeWorkspace), m_special(monitor->m_activeSpecialWorkspace), m_transform(monitor->m_transform),
          m_pixelSize(monitor->m_pixelSize), m_specialDim(Compat::specialDim(monitor)->value()),
          m_specialBlur(Compat::specialBlur(monitor)->value()) {
        // Finish all allocations before mutating any live scene state.
        for (const auto &reference : Compat::workspaceReferences()) {
            const auto workspace = reference.lock();
            if (workspace->m_monitor != monitor)
                continue;
            m_workspaces.push_back({workspace, Compat::workspaceVisible(workspace), workspace->m_forceRendering, workspace->m_alpha->value(),
                                    workspace->m_renderOffset->value()});
        }
        for (const auto &window : Compat::windows()) {
            if (!Compat::windowMapped(window))
                continue;
            m_windows.push_back({window, Compat::windowMapped(window), Compat::position(window)->value(), Compat::size(window)->value(),
                                 Compat::windowFloatingOffset(window),
                                 Compat::windowAlpha(window, Desktop::View::WINDOW_ALPHA_MOVE_TO_WORKSPACE)->value(),
                                 Compat::windowAlpha(window, Desktop::View::WINDOW_ALPHA_MOVE_FROM_WORKSPACE)->value()});
        }
    }

    ~SceneState() {
        if (!m_applied)
            return;
        for (const auto &state : m_windows) {
            const auto &window = state.window;
            Compat::windowMapped(window) = state.mapped;
            Compat::position(window)->value() = state.position;
            Compat::size(window)->value() = state.size;
            Compat::windowFloatingOffset(window) = state.floatingOffset;
            Compat::windowAlpha(window, Desktop::View::WINDOW_ALPHA_MOVE_TO_WORKSPACE)->value() = state.moveToAlpha;
            Compat::windowAlpha(window, Desktop::View::WINDOW_ALPHA_MOVE_FROM_WORKSPACE)->value() = state.moveFromAlpha;
        }
        for (const auto &state : m_workspaces) {
            Compat::setWorkspaceVisible(state.workspace, state.visible);
            state.workspace->m_forceRendering = state.forceRendering;
            state.workspace->m_alpha->value() = state.alpha;
            state.workspace->m_renderOffset->value() = state.offset;
        }
        m_monitor->m_activeWorkspace = m_active;
        m_monitor->m_activeSpecialWorkspace = m_special;
        m_monitor->m_transform = m_transform;
        m_monitor->m_pixelSize = m_pixelSize;
        Compat::specialDim(m_monitor)->value() = m_specialDim;
        Compat::specialBlur(m_monitor)->value() = m_specialBlur;
    }

    void apply(const PHLWORKSPACE &target) {
        m_applied = true;
        m_monitor->m_transform = WL_OUTPUT_TRANSFORM_NORMAL;
        m_monitor->m_pixelSize = m_monitor->m_transformedSize;

        const bool originalScene = target && target == m_active;
        if (!originalScene) {
            m_monitor->m_activeWorkspace = target ? target : m_active;
            m_monitor->m_activeSpecialWorkspace.reset();
            Compat::specialDim(m_monitor)->value() = 0.F;
            Compat::specialBlur(m_monitor)->value() = 0.F;
            for (const auto &state : m_workspaces) {
                const bool selected = state.workspace == target;
                Compat::setWorkspaceVisible(state.workspace, selected);
                state.workspace->m_forceRendering = selected;
                state.workspace->m_alpha->value() = selected ? 1.F : 0.F;
                state.workspace->m_renderOffset->value() = {};
            }
        }
        for (const auto &state : m_windows)
            applyWindow(state.window, target, originalScene);
    }

  private:
    void applyWindow(const PHLWINDOW &window, const PHLWORKSPACE &target, bool originalScene) {
        const bool onMonitor = window->m_monitor == m_monitor;
        const bool pinned = Compat::windowPinned(window);
        const bool included = onMonitor && (originalScene || pinned || (target && window->m_workspace == target));
        if (!included) {
            // Changing the field directly emits no map/unmap, focus, or client configure events.
            Compat::windowMapped(window) = false;
            return;
        }
        if (originalScene || pinned)
            return;

        // Mutable current values preserve the animation goals, clock, velocity, and callbacks.
        // setValueAndWarp would fire callbacks and irreversibly alter a live animation.
        Compat::position(window)->value() = Compat::position(window)->goal();
        Compat::size(window)->value() = Compat::size(window)->goal();
        Compat::clearFloatingOffset(window);
        Compat::windowAlpha(window, Desktop::View::WINDOW_ALPHA_MOVE_TO_WORKSPACE)->value() = 1.F;
        Compat::windowAlpha(window, Desktop::View::WINDOW_ALPHA_MOVE_FROM_WORKSPACE)->value() = 1.F;
    }

    PHLMONITOR m_monitor;
    PHLWORKSPACE m_active;
    PHLWORKSPACE m_special;
    wl_output_transform m_transform;
    Vector2D m_pixelSize;
    float m_specialDim;
    float m_specialBlur;
    std::vector<WorkspaceState> m_workspaces;
    std::vector<WindowState> m_windows;
    bool m_applied = false;
};

#if HYPRFLOW_HYPRLAND_057
// Hyprland 0.57 owns per-frame state in a render context that is inactive between frames.
// A full fake render begins and ends its own session, so nothing outside it needs restoring.
class RenderState {
  public:
    RenderState() : m_renderer(g_pHyprRenderer.get()) {}

    ~RenderState() {
        if (m_begun)
            m_renderer->abortRender();
    }

    bool begin(const PHLMONITOR &monitor, const SP<Render::IFramebuffer> &framebuffer) {
        if (m_renderer->context().active())
            return false;
        CRegion damage{0, 0, framebuffer->m_size.x, framebuffer->m_size.y};
        m_begun = m_renderer->beginFullFakeRender(monitor, damage, framebuffer);
        if (!m_begun)
            return false;
        auto &context = m_renderer->context();
        context.m_blockSurfaceFeedback = true;
        context.m_data.blockScreenShader = true;
        return true;
    }

    void finish() {
        m_renderer->endRender();
        m_begun = false;
    }

    void clear() {
        Render::IHyprRenderer::addPassElement(m_renderer->context(),
                                              makeUnique<CClearPassElement>(CClearPassElement::SClearData{CHyprColor{0, 0, 0, 1}}));
    }

    void renderWorkspace(const PHLMONITOR &monitor, const PHLWORKSPACE &workspace) {
        using RenderWorkspace =
            void (Render::IHyprRenderer::*)(Render::CRenderContext &, PHLMONITOR, PHLWORKSPACE, const Time::steady_tp &, const CBox &);
        const auto render = static_cast<RenderWorkspace>(&RendererAccess::renderWorkspace);
        (m_renderer->*render)(m_renderer->context(), monitor, workspace, Time::steadyNow(), CBox{{0, 0}, monitor->m_pixelSize});
    }

  private:
    Render::IHyprRenderer *m_renderer;
    bool m_begun = false;
};
#else
class RenderState {
  public:
    RenderState()
        : m_renderer(g_pHyprRenderer.get()), m_data(m_renderer->m_renderData), m_mode(m_renderer->*RENDER_MODE),
          m_feedbackBlocked(m_renderer->m_bBlockSurfaceFeedback) {}

    ~RenderState() {
        if (m_begun) {
            m_renderer->m_renderPass.clear();
            try {
                m_renderer->endRender();
            } catch (...) {
                // Scene and renderer flags must still be restored after a failed render.
            }
        }
        m_renderer->m_renderData = std::move(m_data);
        m_renderer->*RENDER_MODE = m_mode;
        m_renderer->m_bBlockSurfaceFeedback = m_feedbackBlocked;
    }

    bool begin(const PHLMONITOR &monitor, const SP<Render::IFramebuffer> &framebuffer) {
        CRegion damage{0, 0, framebuffer->m_size.x, framebuffer->m_size.y};
        m_begun = m_renderer->beginFullFakeRender(monitor, damage, framebuffer);
#ifdef HYPRFLOW_VULKAN
        // The WIP Vulkan fake-render entry point leaves the previous frame's damage unchanged.
        // Every workspace snapshot is a complete replacement, including its first inactive capture.
        if (m_begun)
            (m_renderer->*SET_DAMAGE)(damage, std::nullopt);
#endif
        m_renderer->m_bBlockSurfaceFeedback = true;
        m_renderer->m_renderData.blockScreenShader = true;
        return m_begun;
    }

    void finish() {
        m_renderer->endRender();
        m_begun = false;
    }

    void clear() {
        m_renderer->m_renderPass.add(makeUnique<CClearPassElement>(CClearPassElement::SClearData{CHyprColor{0, 0, 0, 1}}));
    }

    void renderWorkspace(const PHLMONITOR &monitor, const PHLWORKSPACE &workspace) {
        const auto render = &RendererAccess::renderWorkspace;
        (m_renderer->*render)(monitor, workspace, Time::steadyNow(), CBox{{0, 0}, monitor->m_pixelSize});
    }

  private:
    Render::IHyprRenderer *m_renderer;
    Render::SRenderData m_data;
    Render::eRenderMode m_mode;
    bool m_feedbackBlocked;
    bool m_begun = false;
};
#endif

bool canCapture(const PHLMONITOR &monitor, const PHLWORKSPACE &workspace) {
    if (!monitor || !monitor->m_output || !g_pHyprRenderer)
        return false;
#ifndef HYPRFLOW_VULKAN
    if (g_pHyprRenderer->type() != Render::IHyprRenderer::RT_GL)
        return false;
#endif
    if (workspace && workspace->m_monitor != monitor)
        return false;
    return std::min(monitor->m_transformedSize.x, monitor->m_transformedSize.y) >= 1;
}

SP<Render::IFramebuffer> captureTarget(const PHLMONITOR &monitor, const SP<Render::IFramebuffer> &existing) {
    if (existing && existing->m_size == monitor->m_transformedSize && existing->isAllocated())
        return existing;
    auto target = g_pHyprRenderer->createFB("hyprflow workspace");
    if (!target)
        return {};
    if (!target->alloc(monitor->m_transformedSize.x, monitor->m_transformedSize.y, DRM_FORMAT_ARGB8888))
        return {};
    return target;
}

} // namespace

bool captureWorkspace(PHLMONITOR monitor, PHLWORKSPACE workspace, SP<Render::IFramebuffer> &framebuffer) {
    if (!canCapture(monitor, workspace))
        return false;

    try {
#ifndef HYPRFLOW_VULKAN
        Render::GL::g_pHyprOpenGL->makeEGLCurrent();
#endif
        auto target = captureTarget(monitor, framebuffer);
        if (!target)
            return false;
        // Native shadow and color-management passes require metadata, including on reused captures.
        target->setImageDescription(monitor->workBufferImageDescription());

        SceneState scene{monitor};
        RenderState render;
        scene.apply(workspace);
        if (!render.begin(monitor, target))
            return false;

        render.clear();
        // Keeping the original workspace identity for an empty card lets Hyprland render pinned windows in their normal layer order.
        render.renderWorkspace(monitor, workspace ? workspace : monitor->m_activeWorkspace);
        render.finish();
        const auto texture = target->getTexture();
        if (!texture)
            return false;
        texture->m_transform = HYPRUTILS_TRANSFORM_NORMAL;
        framebuffer = std::move(target);
        return true;
    } catch (const std::exception &error) {
        Log::logger->log(Log::ERR, "[hyprflow] workspace capture failed: {}", error.what());
        return false;
    } catch (...) {
        Log::logger->log(Log::ERR, "[hyprflow] workspace capture failed");
        return false;
    }
}

} // namespace Hyprflow

#include "Flow.hpp"
#include "Config.hpp"
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/render/Renderer.hpp>
#include <hyprland/src/render/pass/PassElement.hpp>
#include <hyprland/src/event/EventBus.hpp>
#include <hyprland/src/desktop/state/FocusState.hpp>
#include <hyprland/src/managers/SessionLockManager.hpp>
#include <hyprland/src/config/values/types/IntValue.hpp>
#include <hyprland/src/debug/log/Logger.hpp>
#include <lua.hpp>
#include <memory>

namespace {
HANDLE handle;
std::unique_ptr<Hyprflow::Flow> flow;
SP<Config::Values::CIntValue> workspaceCount;
std::unique_ptr<Hyprflow::FlowConfig> appearanceConfig;
std::vector<CHyprSignalListener> listeners;
uint64_t generation = 0;

void reset() {
    g_pHyprRenderer->m_renderPass.removeAllOfType("HyprflowPass");
    auto released = std::move(flow);
    ++generation;
}

class FlowPass : public IPassElement {
    uint64_t serial = generation;
    PHLMONITOR monitor;

  public:
    explicit FlowPass(PHLMONITOR output) : monitor(output) {}
    std::vector<UP<IPassElement>> draw() override {
        if (flow && serial == generation && !g_pSessionLockManager->isSessionLocked()) {
            try {
                flow->render(appearanceConfig->read());
            } catch (const std::exception &error) {
                Log::logger->log(Log::ERR, "[hyprflow] {}", error.what());
                flow->failed = true;
            }
        }
        return {};
    }
    bool needsLiveBlur() override {
        return false;
    }
    bool needsPrecomputeBlur() override {
        return false;
    }
    const char *passName() override {
        return "HyprflowPass";
    }
    ePassElementType type() override {
        return EK_CUSTOM;
    }
    std::optional<CBox> boundingBox() override {
        return CBox{{}, monitor->m_size};
    }
    CRegion opaqueRegion() override {
        return CBox{{}, monitor->m_size};
    }
};

SDispatchResult action(const std::string &name, const std::string &argument) {
    if (name == "status")
        return {.error = flow ? flow->status() : "{\"open\":false}"};
    if (g_pSessionLockManager->isSessionLocked())
        return {.success = false, .error = "hyprflow: session is locked"};
    if (name == "accept" || name == "cancel") {
        if (flow)
            flow->close(name == "accept");
        return {};
    }
    if (name == "toggle" && flow) {
        flow->toggle();
        return {};
    }
    const bool created = !flow;
    try {
        if (!flow) {
            const auto monitor = Desktop::focusState()->monitor();
            if (!monitor || !monitor->m_activeWorkspace || monitor->m_pixelSize.x < 1 || monitor->m_pixelSize.y < 1)
                return {.success = false, .error = "hyprflow: no usable focused monitor"};
            flow = std::make_unique<Hyprflow::Flow>(monitor, std::clamp<int>(workspaceCount->value(), 1, 32));
        }
        if (name == "left" || name == "right")
            flow->move(name == "left" ? -1 : 1);
        if (name == "jump" && !flow->jump(argument)) {
            if (created)
                reset();
            return {.success = false, .error = "hyprflow: workspace is absent or belongs to another monitor"};
        }
    } catch (const std::exception &error) {
        reset();
        return {.success = false, .error = error.what()};
    }
    return {};
}

template <int Index> int luaAction(lua_State *state) {
    constexpr const char *names[] = {"toggle", "left", "right", "jump", "accept", "cancel", "status"};
    const char *argument = luaL_optstring(state, 1, "");
    auto result = action(names[Index], argument);
    if (!result.success)
        return luaL_error(state, "%s", result.error.c_str());
    lua_pushlstring(state, result.error.data(), result.error.size());
    return 1;
}

void registerInput() {
    auto *bus = Event::bus().get();
    listeners.push_back(bus->m_events.input.mouse.move.listen([](Vector2D, Event::SCallbackInfo &info) {
        if (flow)
            info.cancelled = true;
    }));
    listeners.push_back(bus->m_events.input.mouse.button.listen([](IPointer::SButtonEvent, Event::SCallbackInfo &info) {
        if (flow)
            info.cancelled = true;
    }));
    listeners.push_back(bus->m_events.input.mouse.axis.listen([](IPointer::SAxisEvent, Event::SCallbackInfo &info) {
        if (flow)
            info.cancelled = true;
    }));
    listeners.push_back(bus->m_events.input.keyboard.focus.listen([](SP<CWLSurfaceResource> surface) {
        if (flow && !flow->finished && surface && !g_pSessionLockManager->isSessionLocked())
            Desktop::focusState()->rawSurfaceFocus(nullptr, nullptr);
    }));
    listeners.push_back(bus->m_events.input.touch.down.listen([](ITouch::SDownEvent, Event::SCallbackInfo &info) {
        if (flow)
            info.cancelled = true;
    }));
    listeners.push_back(bus->m_events.input.touch.up.listen([](ITouch::SUpEvent, Event::SCallbackInfo &info) {
        if (flow)
            info.cancelled = true;
    }));
    listeners.push_back(bus->m_events.input.touch.motion.listen([](ITouch::SMotionEvent, Event::SCallbackInfo &info) {
        if (flow)
            info.cancelled = true;
    }));
}
} // namespace

APICALL EXPORT std::string PLUGIN_API_VERSION() {
    return HYPRLAND_API_VERSION;
}

APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE pluginHandle) {
    handle = pluginHandle;
    if (std::string(__hyprland_api_get_hash()) != __hyprland_api_get_client_hash())
        throw std::runtime_error("hyprflow: headers do not match the running Hyprland ABI");
    if (g_pHyprRenderer->type() != Render::IHyprRenderer::RT_GL)
        throw std::runtime_error("hyprflow requires the OpenGL renderer");
    workspaceCount = makeShared<Config::Values::CIntValue>("plugin:hyprflow:workspace_count", "Number of default numeric workspace cards", 9,
                                                           Config::Values::SIntValueOptions{.min = 1, .max = 32});
    HyprlandAPI::addConfigValueV2(handle, workspaceCount);
    appearanceConfig = std::make_unique<Hyprflow::FlowConfig>(handle);
    const char *names[] = {"toggle", "left", "right", "jump", "accept", "cancel", "status"};
    PLUGIN_LUA_FN callbacks[] = {luaAction<0>, luaAction<1>, luaAction<2>, luaAction<3>, luaAction<4>, luaAction<5>, luaAction<6>};
    for (size_t i = 0; i < std::size(names); ++i) {
        const std::string name = names[i];
        HyprlandAPI::addDispatcherV2(handle, "hyprflow:" + name, [name](const std::string &argument) { return action(name, argument); });
        HyprlandAPI::addLuaFunction(handle, "hyprflow", name, callbacks[i]);
    }
    listeners.push_back(Event::bus()->m_events.render.pre.listen([](PHLMONITOR monitor) {
        if (!flow || flow->monitor != monitor || flow->capturing)
            return;
        if (g_pSessionLockManager->isSessionLocked() || flow->finished || flow->failed) {
            reset();
            return;
        }
        try {
            flow->preRender(appearanceConfig->read().workspaceOverlay);
            if (flow->finished)
                reset();
        } catch (const std::exception &error) {
            Log::logger->log(Log::ERR, "[hyprflow] {}", error.what());
            reset();
        }
    }));
    listeners.push_back(Event::bus()->m_events.render.stage.listen([](eRenderStage stage) {
        if (!flow || flow->capturing || stage != RENDER_LAST_MOMENT || g_pSessionLockManager->isSessionLocked())
            return;
        if (g_pHyprRenderer->m_renderData.pMonitor != flow->monitor)
            return;
        g_pHyprRenderer->m_renderPass.add(makeUnique<FlowPass>(flow->monitor));
        g_pHyprRenderer->damageMonitor(flow->monitor);
    }));
    listeners.push_back(Event::bus()->m_events.monitor.removed.listen([](PHLMONITOR monitor) {
        if (flow && flow->monitor == monitor)
            reset();
    }));
    listeners.push_back(g_pSessionLockManager->m_events.lock.listen([]() { reset(); }));
    listeners.push_back(Event::bus()->m_events.config.reloaded.listen([]() { appearanceConfig->read(); }));
    registerInput();
    return {"hyprflow", "Classic Cover Flow workspace navigation", "hyprflow contributors", "0.1.0"};
}

APICALL EXPORT void PLUGIN_EXIT() {
    listeners.clear();
    reset();
    appearanceConfig.reset();
    workspaceCount.reset();
}

#include <hyprland/src/desktop/state/FocusState.hpp>
#include <hyprland/src/event/EventBus.hpp>
#include <hyprland/src/helpers/Monitor.hpp>
#include <hyprland/src/managers/KeybindManager.hpp>
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <lua.hpp>
#include <stdexcept>
#include <string>

namespace {
struct RestoreTransform {
  PHLMONITOR monitor;
  wl_output_transform original;
  ~RestoreTransform() { monitor->m_transform = original; }
};
int unsupportedOpen(lua_State *state) {
  const auto monitor = Desktop::focusState()->monitor();
  if (!monitor)
    return luaL_error(state, "No owned test output");
  SDispatchResult result;
  {
    RestoreTransform restore{monitor, monitor->m_transform};
    monitor->m_transform = WL_OUTPUT_TRANSFORM_90;
    result = g_pKeybindManager->m_dispatchers.at("hyprflow:toggle")("");
  }
  lua_pushboolean(state, result.success);
  lua_pushlstring(state, result.error.data(), result.error.size());
  return 2;
}
int unsupportedAction(lua_State *state) {
  const std::string name = luaL_checkstring(state, 1);
  if (name != "accept" && name != "cancel")
    return luaL_error(state, "Guard probe accepts only accept/cancel");
  const auto monitor = Desktop::focusState()->monitor();
  if (!monitor)
    return luaL_error(state, "No owned test output");
  SDispatchResult result;
  {
    RestoreTransform restore{monitor, monitor->m_transform};
    monitor->m_transform = WL_OUTPUT_TRANSFORM_90;
    result = g_pKeybindManager->m_dispatchers.at("hyprflow:" + name)("");
  }
  lua_pushboolean(state, result.success);
  lua_pushlstring(state, result.error.data(), result.error.size());
  return 2;
}
int unsupportedPreRender(lua_State *state) {
  const auto monitor = Desktop::focusState()->monitor();
  if (!monitor)
    return luaL_error(state, "No owned test output");
  {
    RestoreTransform restore{monitor, monitor->m_transform};
    monitor->m_transform = WL_OUTPUT_TRANSFORM_90;
    Event::bus()->m_events.render.pre.emit(monitor);
  }
  return 0;
}
} // namespace
APICALL EXPORT std::string PLUGIN_API_VERSION() { return HYPRLAND_API_VERSION; }
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE handle) {
  if (std::string(__hyprland_api_get_hash()) !=
      __hyprland_api_get_client_hash())
    throw std::runtime_error("Guard probe SDK mismatch");
  HyprlandAPI::addLuaFunction(handle, "hyprflow_guard_probe",
                              "unsupported_open", unsupportedOpen);
  HyprlandAPI::addLuaFunction(handle, "hyprflow_guard_probe",
                              "unsupported_pre_render", unsupportedPreRender);
  HyprlandAPI::addLuaFunction(handle, "hyprflow_guard_probe",
                              "unsupported_action", unsupportedAction);
  return {"hyprflow_guard_probe", "Owned-session atomic output guard probe",
          "hyprflow tests", "0"};
}

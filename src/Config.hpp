#pragma once

#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/config/shared/complex/ComplexDataTypes.hpp>
#include <hyprland/src/config/values/types/FloatValue.hpp>
#include <hyprland/src/config/values/types/IntValue.hpp>
#include <hyprland/src/config/values/types/StringValue.hpp>
#include <array>
#include <optional>
#include <string>

namespace Hyprflow {

struct FlowAppearance {
    double workspaceScale = 1.0;
    double workspaceSpread = 0.18;
    int borderWidth = 0;
    bool workspaceOverlay = false, showLabels = true;
    double backgroundOpacity = 1.0, backgroundBlur = 0.0, reflectionOpacity = 0.34, centerY = 0.4;
    CHyprColor backgroundColor{0.F, 0.F, 0.F, 1.F};
    // Base, current, focused. Empty overrides inherit the next applicable border.
    std::array<::Config::CGradientValueData, 3> borders{::Config::CGradientValueData{CHyprColor{1.F, 1.F, 1.F, 1.F}}, {}, {}};
};

class FlowConfig {
  public:
    explicit FlowConfig(HANDLE handle);
    ~FlowConfig() = default;
    const FlowAppearance &read();

  private:
    void readScalars();
    void readBorders();
    void reject(const char *option, const std::string &reason);
    void rejectScalar(size_t index, const char *option, const std::string &value, const char *reason);

    HANDLE handle;
    SP<::Config::Values::CFloatValue> workspaceScale;
    SP<::Config::Values::CFloatValue> workspaceSpread;
    SP<::Config::Values::CIntValue> borderWidth;
    std::array<SP<::Config::Values::CStringValue>, 3> borderColors;
    // Background opacity, blur radius, reflection opacity, vertical center.
    std::array<SP<::Config::Values::CFloatValue>, 4> effects;
    std::array<SP<::Config::Values::CIntValue>, 2> switches;
    SP<::Config::Values::CStringValue> backgroundColor;
    std::optional<std::string> lastBackgroundText;
    std::array<std::optional<std::string>, 3> lastBorderText;
    std::array<std::optional<std::string>, 9> lastRejectedScalar;
    FlowAppearance appearance;
};

} // namespace Hyprflow

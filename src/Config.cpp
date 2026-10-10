#include "Config.hpp"
#include "Motion.hpp"
#include <hyprland/src/config/shared/parserUtils/ParserUtils.hpp>
#include <hyprland/src/debug/log/Logger.hpp>
#include <algorithm>
#include <charconv>
#include <cctype>
#include <cmath>
#include <expected>
#include <format>
#include <numbers>
#include <sstream>
#include <stdexcept>
#include <string_view>
#include <vector>

namespace Hyprflow {
namespace {
bool whitespace(char value) {
    return std::isspace(static_cast<unsigned char>(value));
}

bool emptySpec(const std::string &text) {
    return std::ranges::all_of(text, whitespace);
}

// The native border shader has ten equally spaced color stops.
constexpr size_t maxBorderColors = 10;

std::expected<std::vector<std::string>, std::string> borderTokens(const std::string &text) {
    std::istringstream input{text};
    std::vector<std::string> tokens;
    std::string token;
    while (input >> token) {
        tokens.push_back(std::move(token));
        if (tokens.size() > maxBorderColors + 1)
            return std::unexpected("border requires at most ten colors and one angle");
    }
    if (tokens.empty())
        return std::unexpected("border requires at least one color");
    return tokens;
}

std::expected<double, std::string> angleNumber(std::string_view number) {
    if (number.starts_with('+')) {
        number.remove_prefix(1);
        if (number.starts_with('-') || number.starts_with('+'))
            return std::unexpected("border angle must have at most one sign");
    }
    double angle = 0.0;
    const auto result = std::from_chars(number.data(), number.data() + number.size(), angle);
    if (result.ec != std::errc{} || result.ptr != number.data() + number.size() || !std::isfinite(angle))
        return std::unexpected("border angle must be a finite number followed by deg");
    return angle;
}

std::expected<double, std::string> borderAngle(std::vector<std::string> &tokens) {
    const std::string_view token = tokens.back();
    if (!token.ends_with("deg"))
        return 0.0;
    const auto number = angleNumber(token.substr(0, token.size() - 3));
    if (!number)
        return std::unexpected(number.error());
    // Match native whole-degree rendering, while safely normalizing signed angles.
    double angle = std::fmod(std::trunc(*number), 360.0);
    if (angle < 0.0)
        angle += 360.0;
    tokens.pop_back();
    return angle;
}

std::optional<std::string_view> colorHex(std::string_view token) {
    struct Format {
        std::string_view prefix, suffix;
        size_t digits = 0;
    };
    constexpr Format formats[] = {{"0x", "", 8}, {"rgb(", ")", 6}, {"rgba(", ")", 8}};
    for (const auto &format : formats) {
        if (token.starts_with(format.prefix) && token.ends_with(format.suffix) &&
            token.size() == format.prefix.size() + format.digits + format.suffix.size())
            return token.substr(format.prefix.size(), format.digits);
    }
    return std::nullopt;
}

std::expected<CHyprColor, std::string> borderColor(std::string_view token) {
    // Hyprexpo's documented hex forms, parsed by Hyprland for identical channel ordering.
    const auto hex = colorHex(token);
    if (!hex)
        return std::unexpected("border colors require rgb(RRGGBB), rgba(RRGGBBAA), or 0xAARRGGBB");
    if (!std::ranges::all_of(*hex, [](unsigned char value) { return std::isxdigit(value); }))
        return std::unexpected("border color contains invalid hexadecimal digits");
    const auto parsed = ::Config::ParserUtils::parseColor(token);
    if (!parsed)
        return std::unexpected(parsed.error());
    return CHyprColor{static_cast<uint64_t>(*parsed)};
}

std::expected<::Config::CGradientValueData, std::string> parseBorderSpec(const std::string &text) {
    auto tokens = borderTokens(text);
    if (!tokens)
        return std::unexpected(tokens.error());
    const auto angle = borderAngle(*tokens);
    if (!angle)
        return std::unexpected(angle.error());
    if (tokens->empty() || tokens->size() > maxBorderColors)
        return std::unexpected("border requires one to ten colors");

    std::vector<CHyprColor> colors;
    colors.reserve(tokens->size());
    for (const auto &token : *tokens) {
        const auto parsed = borderColor(token);
        if (!parsed)
            return std::unexpected(parsed.error());
        colors.push_back(*parsed);
    }
    return ::Config::CGradientValueData{std::move(colors), static_cast<float>(*angle * std::numbers::pi / 180.0)};
}

std::expected<void, std::string> validateBorder(const std::string &text, bool allowEmpty) {
    if (allowEmpty && emptySpec(text))
        return {};
    const auto parsed = parseBorderSpec(text);
    if (!parsed)
        return std::unexpected(parsed.error());
    return {};
}
} // namespace

FlowConfig::FlowConfig(HANDLE handle)
    : handle(handle), workspaceScale(makeShared<::Config::Values::CFloatValue>("plugin:hyprflow:workspace_scale", "Flow workspace size multiplier",
                                                                               1.F, ::Config::Values::SFloatValueOptions{.min = .1F, .max = 2.F})),
      workspaceSpread(makeShared<::Config::Values::CFloatValue>("plugin:hyprflow:workspace_spread",
                                                                "Inactive workspace spacing relative to card width", .18F,
                                                                ::Config::Values::SFloatValueOptions{.min = 0.F, .max = 1.F})),
      borderWidth(makeShared<::Config::Values::CIntValue>("plugin:hyprflow:border_width", "Workspace border width in logical pixels", 0,
                                                          ::Config::Values::SIntValueOptions{.min = 0, .max = 32})) {
    const char *names[] = {"plugin:hyprflow:border_color", "plugin:hyprflow:border_color_current", "plugin:hyprflow:border_color_focus"};
    for (size_t index = 0; index < borderColors.size(); ++index) {
        const bool allowEmpty = index != 0;
        borderColors[index] = makeShared<::Config::Values::CStringValue>(
            names[index], "Workspace border color or gradient", allowEmpty ? "" : "rgba(ffffffff)",
            ::Config::Values::SStringValueOptions{.validator = [allowEmpty](const std::string &text) { return validateBorder(text, allowEmpty); }});
    }
    const auto add = [handle](SP<::Config::Values::IValue> value) {
        if (!HyprlandAPI::addConfigValueV2(handle, value))
            throw std::runtime_error(std::string("hyprflow: failed to register ") + value->name());
    };
    add(workspaceScale);
    add(workspaceSpread);
    add(borderWidth);
    constexpr const char *effectNames[] = {"plugin:hyprflow:background_opacity", "plugin:hyprflow:background_blur",
                                           "plugin:hyprflow:reflection_opacity", "plugin:hyprflow:center_y"};
    constexpr float defaults[] = {1.F, 0.F, .34F, .4F}, maxima[] = {1.F, 64.F, 1.F, 1.F};
    for (size_t i = 0; i < effects.size(); ++i) {
        effects[i] = makeShared<::Config::Values::CFloatValue>(effectNames[i], "Flow backdrop and composition", defaults[i],
                                                               ::Config::Values::SFloatValueOptions{.min = 0.F, .max = maxima[i]});
        add(effects[i]);
    }
    constexpr const char *switchNames[] = {"plugin:hyprflow:workspace_overlay", "plugin:hyprflow:show_labels"};
    for (size_t i = 0; i < switches.size(); ++i) {
        switches[i] = makeShared<::Config::Values::CIntValue>(switchNames[i], "Enable flow appearance feature", i == 0 ? 0 : 1,
                                                              ::Config::Values::SIntValueOptions{.min = 0, .max = 1});
        add(switches[i]);
    }
    backgroundColor = makeShared<::Config::Values::CStringValue>(
        "plugin:hyprflow:background_color", "Backdrop tint color", "rgb(000000)",
        ::Config::Values::SStringValueOptions{.validator = [](const std::string &text) -> std::expected<void, std::string> {
            const auto parsed = borderColor(text);
            if (!parsed)
                return std::unexpected(parsed.error());
            return {};
        }});
    add(backgroundColor);
    for (const auto &color : borderColors)
        add(color);
}

void FlowConfig::reject(const char *option, const std::string &reason) {
    const auto message = std::format("[hyprflow] rejected {}: {}; retaining the previous value", option, reason);
    Log::logger->log(Log::ERR, "{}", message);
    HyprlandAPI::addNotification(handle, message, CHyprColor{1.F, .35F, .2F, 1.F}, 5000.F);
}

void FlowConfig::rejectScalar(size_t index, const char *option, const std::string &value, const char *reason) {
    if (lastRejectedScalar[index] == value)
        return;
    lastRejectedScalar[index] = value;
    reject(option, reason);
}

void FlowConfig::readScalars() {
    const auto scale = workspaceScale->value();
    if (validSetting(scale, .1, 2.0)) {
        appearance.workspaceScale = scale;
        lastRejectedScalar[0].reset();
    } else
        rejectScalar(0, "workspace_scale", std::format("{}", scale), "must be finite and between 0.1 and 2");
    const auto spread = workspaceSpread->value();
    if (validSetting(spread, 0.0, 1.0)) {
        // Preserve the original double-precision default through the float config API.
        appearance.workspaceSpread = spread == .18F ? .18 : static_cast<double>(spread);
        lastRejectedScalar[1].reset();
    } else
        rejectScalar(1, "workspace_spread", std::format("{}", spread), "must be finite and between 0 and 1");
    const auto width = borderWidth->value();
    if (validSetting(static_cast<double>(width), 0.0, 32.0)) {
        appearance.borderWidth = static_cast<int>(width);
        lastRejectedScalar[2].reset();
    } else
        rejectScalar(2, "border_width", std::format("{}", width), "must be between 0 and 32");
    constexpr const char *names[] = {"background_opacity", "background_blur", "reflection_opacity", "center_y"};
    constexpr double maxima[] = {1, 64, 1, 1};
    double *destinations[] = {&appearance.backgroundOpacity, &appearance.backgroundBlur, &appearance.reflectionOpacity, &appearance.centerY};
    for (size_t i = 0; i < effects.size(); ++i) {
        const double value = effects[i]->value();
        if (validSetting(value, 0, maxima[i])) {
            *destinations[i] = value;
            lastRejectedScalar[3 + i].reset();
        } else
            rejectScalar(3 + i, names[i], std::format("{}", value), "outside the finite documented range");
    }
    constexpr const char *switchNames[] = {"workspace_overlay", "show_labels"};
    bool *flags[] = {&appearance.workspaceOverlay, &appearance.showLabels};
    for (size_t i = 0; i < switches.size(); ++i) {
        const auto value = switches[i]->value();
        if (value == 0 || value == 1) {
            *flags[i] = value == 1;
            lastRejectedScalar[7 + i].reset();
        } else
            rejectScalar(7 + i, switchNames[i], std::format("{}", value), "must be 0 or 1");
    }
}

void FlowConfig::readBorders() {
    constexpr const char *names[] = {"border_color", "border_color_current", "border_color_focus"};
    for (size_t index = 0; index < borderColors.size(); ++index) {
        const std::string text = borderColors[index]->value();
        if (lastBorderText[index] && *lastBorderText[index] == text)
            continue;
        lastBorderText[index] = text;
        if (index != 0 && emptySpec(text)) {
            appearance.borders[index] = {};
            continue;
        }
        auto parsed = parseBorderSpec(text);
        if (parsed)
            appearance.borders[index] = std::move(*parsed);
        else
            reject(names[index], parsed.error());
    }
}

const FlowAppearance &FlowConfig::read() {
    readScalars();
    readBorders();
    const std::string text = backgroundColor->value();
    if (lastBackgroundText != text) {
        lastBackgroundText = text;
        const auto parsed = borderColor(text);
        if (parsed)
            appearance.backgroundColor = *parsed;
        else
            reject("background_color", parsed.error());
    }
    return appearance;
}

} // namespace Hyprflow

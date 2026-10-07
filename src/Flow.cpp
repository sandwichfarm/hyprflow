#include "Flow.hpp"
#include "Config.hpp"
#include "Capture.hpp"
#include <hyprland/src/render/Renderer.hpp>
#include <hyprland/src/desktop/Workspace.hpp>
#include <hyprland/src/state/WorkspaceState.hpp>
#include <hyprland/src/desktop/state/FocusState.hpp>
#include <hyprland/src/managers/KeybindManager.hpp>
#include <hyprland/src/animation/WorkspaceAnimationController.hpp>
#include <hyprland/src/output/Monitor.hpp>
#include <algorithm>
#include <numeric>
#include <format>

namespace Hyprflow {
namespace {
void submap(const std::string &name) {
    g_pKeybindManager->m_dispatchers.at("submap")(name.empty() ? "reset" : name);
}
} // namespace

Flow::Flow(PHLMONITOR output, int workspaceCount) : monitor(output), lastFrame(Time::steadyNow()) {
    auto workspaces = State::workspaceState()->workspacesCopy();
    for (int id = 1; id <= workspaceCount; ++id) {
        const auto found = std::ranges::find_if(workspaces, [id](const auto &w) { return w->m_id == id; });
        if (found != workspaces.end() && (*found)->m_monitor != monitor)
            continue;
        cards.push_back({id, std::to_string(id), found == workspaces.end() ? nullptr : *found, {}});
    }
    for (const auto &workspace : workspaces) {
        if (workspace->m_monitor != monitor || workspace->m_isSpecialWorkspace || workspace->inert())
            continue;
        auto found = std::ranges::find_if(cards, [&](const Card &card) { return card.id == workspace->m_id; });
        if (found == cards.end())
            cards.push_back({workspace->m_id, workspace->m_name, workspace, {}});
        else
            found->name = workspace->m_name;
    }
    std::ranges::sort(cards, {}, &Card::id);
    const auto selected = std::ranges::find_if(cards, [&](const Card &card) { return card.workspace == monitor->m_activeWorkspace; });
    if (selected == cards.end())
        throw std::runtime_error("hyprflow: no active workspace in flow");
    origin = anchor = std::distance(cards.begin(), selected);
    focus.value = focus.target = origin;
    openness.target = 1;
    previousSubmap = g_pKeybindManager->getCurrentSubmap().name;
    previousFocus = Desktop::focusState()->window();
    previousScanoutBlock = g_pHyprRenderer->m_directScanoutBlocked;
    g_pHyprRenderer->m_directScanoutBlocked = true;
    submap("hyprflow");
    Desktop::focusState()->rawSurfaceFocus(nullptr, nullptr);
    g_pHyprRenderer->damageMonitor(monitor);
}

Flow::~Flow() {
    submap(previousSubmap);
    if (!finished && previousFocus)
        Desktop::focusState()->fullWindowFocus(previousFocus.lock(), Desktop::FOCUS_REASON_KEYBIND);
    g_pHyprRenderer->m_directScanoutBlocked = previousScanoutBlock;
    g_pHyprRenderer->damageMonitor(monitor);
}

void Flow::move(int direction) {
    reopen();
    focus.target = std::clamp(focus.target + direction, 0.0, static_cast<double>(cards.size() - 1));
}

bool Flow::jump(const std::string &workspace) {
    const auto token = workspace.starts_with("name:") ? workspace.substr(5) : workspace;
    const auto found = std::ranges::find_if(cards, [&](const Card &card) { return std::to_string(card.id) == token || card.name == token; });
    if (found == cards.end())
        return false;
    reopen();
    focus.target = std::distance(cards.begin(), found);
    return true;
}

void Flow::close(bool commit) {
    if (closing && committing == commit)
        return;
    reopen();
    closing = true;
    committing = commit;
    if (!commit)
        focus.target = origin;
    // Reversing entry on its original card does not need a detour through fully open.
    if (focus.settled() && static_cast<size_t>(focus.target) == anchor) {
        openness.target = 0;
        exitStarted = true;
    }
}

void Flow::toggle() {
    if (closing)
        reopen();
    else
        close(false);
}

void Flow::reopen() {
    closing = exitStarted = false;
    openness.target = 1;
    g_pHyprRenderer->damageMonitor(monitor);
}

void Flow::refresh() {
    capturing = true;
    const auto nearest = static_cast<size_t>(std::clamp(std::round(focus.value), 0.0, static_cast<double>(cards.size() - 1)));
    for (size_t i = 0; i < cards.size(); ++i) {
        auto &card = cards[i];
        const bool visible = std::abs(static_cast<double>(i) - focus.value) <= 5.5 || i == anchor;
        if (!visible) {
            card.framebuffer.reset();
            continue;
        }
        if (card.workspace && card.workspace->inert())
            card.workspace.reset();
        if (!card.framebuffer || i == nearest) {
            if (!captureWorkspace(monitor, card.workspace, card.framebuffer)) {
                capturing = false;
                throw std::runtime_error("hyprflow: workspace capture failed");
            }
        }
    }
    capturing = false;
}

void Flow::finish() {
    finished = true;
    auto &card = cards[static_cast<size_t>(focus.target)];
    if (committing && !card.workspace)
        card.workspace = State::workspaceState()->create(card.id, monitor->m_id, card.name);
    if (card.workspace && card.workspace != monitor->m_activeWorkspace) {
        auto old = monitor->m_activeWorkspace;
        monitor->changeWorkspace(card.workspace, false, true, false);
        Animation::Workspace::startAnimation(old, Animation::Workspace::ANIMATION_TYPE_OUT, true, true);
        Animation::Workspace::startAnimation(card.workspace, Animation::Workspace::ANIMATION_TYPE_IN, true, true);
    }
    if (!committing && previousFocus)
        Desktop::focusState()->fullWindowFocus(previousFocus.lock(), Desktop::FOCUS_REASON_KEYBIND);
    else if (card.workspace)
        Desktop::focusState()->fullWindowFocus(card.workspace->getFocusCandidate(), Desktop::FOCUS_REASON_KEYBIND);
}

void Flow::preRender() {
    if (monitor->m_activeWorkspace != cards[origin].workspace) {
        finished = true;
        return;
    }
    const auto now = Time::steadyNow();
    const double elapsed = std::chrono::duration<double>(now - lastFrame).count();
    lastFrame = now;
    // Capture before starting the clock: an initial batch cannot skip entry frames.
    const bool first = !cards[origin].framebuffer;
    if (first) {
        refresh();
        lastFrame = Time::steadyNow();
        return;
    }
    focus.advance(elapsed);
    openness.advance(elapsed);
    refresh();
    if (closing && !exitStarted && focus.settled() && openness.settled()) {
        anchor = static_cast<size_t>(focus.target);
        openness.target = 0;
        exitStarted = true;
    }
    if (exitStarted && openness.settled(.00001))
        finish();
}

void Flow::decorateBorder(Quad &quad, size_t index, const FlowAppearance &appearance, const Vector2D &extent, double progress) const {
    if (appearance.borderWidth <= 0)
        return;
    const auto &borders = appearance.borders;
    size_t role = 0;
    if (index == origin && !borders[1].m_colors.empty())
        role = 1;
    if (index == static_cast<size_t>(focus.target) && !borders[2].m_colors.empty())
        role = 2;
    const auto &border = borders[role];
    quad.borderColorCount = std::min<size_t>(border.m_colors.size(), 10);
    std::copy_n(border.m_colorsOkLabA.begin(), quad.borderColorCount * 4, quad.borderColors.begin());
    quad.borderAngle = border.m_angle;
    const double thickness = appearance.borderWidth * monitor->m_scale * smooth(progress);
    quad.borderThickness = {static_cast<float>(thickness / extent.x), static_cast<float>(thickness / extent.y)};
}

Quad Flow::cardQuad(size_t index, bool reflection, const FlowAppearance &appearance) const {
    const double width = monitor->m_transformedSize.x, height = monitor->m_transformedSize.y;
    const double side = cardSide(width, height, appearance.workspaceScale), cx = .5 * width, cy = .4 * height;
    const double p = std::clamp(openness.value, 0.0, 1.0);
    const auto state = pose(static_cast<double>(index) - focus.value, appearance.workspaceSpread);
    const bool anchored = index == anchor && !reflection;
    Quad quad;
    quad.texture = cards[index].framebuffer->getTexture();
    quad.reflection = reflection;
    quad.opacity = anchored ? 1 : smooth(p);
    quad.opacity *= 1 - smooth(std::abs(static_cast<double>(index) - focus.value) - 4.5);
    if (anchored)
        quad.opacity = std::lerp(1.0, static_cast<double>(quad.opacity), p);
    quad.shade = anchored ? std::lerp(1.0, state.shade, p) : state.shade;
    quad.lightDirection = state.yaw < 0 ? 1 : -1;
    const double aspect = width / height;
    quad.imageWidth = std::min(1.0, aspect);
    quad.imageHeight = std::min(1.0, 1 / aspect);
    Vector2D extent{side, side};
    if (anchored) {
        const double w = std::lerp(width, side, p), h = std::lerp(height, side, p);
        extent = {w, h};
        const double fit = std::min(w / width, h / height);
        quad.imageWidth = width * fit / w;
        quad.imageHeight = height * fit / h;
    }
    decorateBorder(quad, index, appearance, extent, p);
    for (size_t i = 0; i < 4; ++i) {
        const double u = (i % 2) - .5, v = (i / 2) - .5;
        auto point = project(state, u, reflection ? 1 - v : v);
        point.x = cx + side * point.x;
        point.y = cy + side * point.y;
        if (anchored)
            point = morph({(u + .5) * width, (v + .5) * height, 1}, point, p);
        quad.points[i] = point;
    }
    return quad;
}

void Flow::render(const FlowAppearance &appearance) {
    std::vector<size_t> order(cards.size());
    std::iota(order.begin(), order.end(), 0);
    std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
        return std::abs(static_cast<double>(a) - focus.value) > std::abs(static_cast<double>(b) - focus.value);
    });
    std::vector<Quad> quads;
    for (bool reflection : {true, false}) {
        for (auto i : order) {
            if (cards[i].framebuffer)
                quads.push_back(cardQuad(i, reflection, appearance));
        }
    }
    const size_t current = std::clamp(std::lround(focus.value), 0L, static_cast<long>(cards.size() - 1));
    if (!label || labelIndex != current) {
        const auto &card = cards[current];
        const auto text = card.name == std::to_string(card.id) ? "Workspace " + card.name : card.name;
        label = g_pHyprRenderer->renderText(text, CHyprColor{.85, .85, .85, 1}, 20 * monitor->m_scale);
        labelIndex = current;
    }
    if (label) {
        Quad caption;
        caption.texture = label;
        caption.opacity = smooth(openness.value);
        const double x = (monitor->m_transformedSize.x - label->m_size.x) / 2;
        const double side = cardSide(monitor->m_transformedSize.x, monitor->m_transformedSize.y, appearance.workspaceScale);
        const double y =
            std::min(monitor->m_transformedSize.y * .4 + side * .70, monitor->m_transformedSize.y - label->m_size.y - 8 * monitor->m_scale);
        caption.points = {{{x, y, 1}, {x + label->m_size.x, y, 1}, {x, y + label->m_size.y, 1}, {x + label->m_size.x, y + label->m_size.y, 1}}};
        quads.push_back(caption);
    }
    renderer.draw(quads, monitor->m_transformedSize.x, monitor->m_transformedSize.y);
}

std::string Flow::status() const {
    const auto &card = cards[static_cast<size_t>(focus.target)];
    return std::format("{{\"open\":true,\"selected\":{},\"origin\":{},\"position\":{:.6f},\"openness\":{:.6f},\"closing\":{}}}", card.id,
                       cards[origin].id, focus.value, openness.value, closing);
}
} // namespace Hyprflow

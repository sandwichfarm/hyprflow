#pragma once
#include "Motion.hpp"
#include <hyprland/src/render/Texture.hpp>
#include <hyprland/src/render/Framebuffer.hpp>
#include <vector>

namespace Hyprflow {
struct Quad {
    std::array<Point, 4> points{};
    SP<Render::ITexture> texture;
    float opacity = 1, shade = 1, imageWidth = 1, imageHeight = 1, lightDirection = 0;
    bool reflection = false;
    float reflectionOpacity = .34F, blurRadius = 0;
    bool backdrop = false, workspaceOverlay = false;
    std::array<float, 4> tint{};
    std::array<float, 40> borderColors{}; // Native Hyprland Oklab+alpha stops, owned by this draw.
    std::array<float, 2> borderThickness{};
    int borderColorCount = 0;
    float borderAngle = 0;
};

// Owns resources for the selected build backend; draws only inside that compositor render pass.
class FlowRenderer {
  public:
    FlowRenderer() = default;
    FlowRenderer(const FlowRenderer &) = delete;
    FlowRenderer &operator=(const FlowRenderer &) = delete;
    ~FlowRenderer();
    void draw(const std::vector<Quad> &quads, int width, int height);

  private:
#ifdef HYPRFLOW_VULKAN
    struct VulkanState;
    VulkanState *vulkan = nullptr;
#endif
    void initialize();
    GLuint blurredTexture(const Quad &quad, int width, int height);
    GLuint program = 0, buffer = 0, vao = 0, blurSampler = 0;
    std::array<SP<Render::IFramebuffer>, 2> blurBuffers;
};
} // namespace Hyprflow

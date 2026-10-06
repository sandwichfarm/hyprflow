#pragma once
#include "Motion.hpp"
#include <hyprland/src/render/Texture.hpp>
#include <vector>

namespace Hyprflow {
struct Quad {
    std::array<Point, 4> points{};
    SP<Render::ITexture> texture;
    float opacity = 1, shade = 1, imageWidth = 1, imageHeight = 1, lightDirection = 0;
    bool reflection = false;
    std::array<float, 40> borderColors{}; // Native Hyprland Oklab+alpha stops, owned by this draw.
    std::array<float, 2> borderThickness{};
    int borderColorCount = 0;
    float borderAngle = 0;
};

// Owns GL objects only. All draw calls run inside the compositor's GL pass.
class FlowRenderer {
  public:
    ~FlowRenderer();
    void draw(const std::vector<Quad> &quads, int width, int height);

  private:
    void initialize();
    GLuint program = 0, buffer = 0, vao = 0;
};
} // namespace Hyprflow

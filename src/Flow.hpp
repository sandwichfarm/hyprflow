#pragma once
#include "FlowRenderer.hpp"
#include <hyprland/src/render/Framebuffer.hpp>
#include <hyprland/src/desktop/DesktopTypes.hpp>
#include <hyprland/src/helpers/time/Time.hpp>
#include <string>

namespace Hyprflow {
struct Card {
    WORKSPACEID id;
    std::string name;
    PHLWORKSPACE workspace;
    SP<Render::IFramebuffer> framebuffer;
};

class Flow {
  public:
    explicit Flow(PHLMONITOR monitor, int workspaceCount);
    ~Flow();
    void preRender();
    void render();
    void move(int direction);
    bool jump(const std::string &workspace);
    void close(bool commit);
    void toggle();
    void reopen();
    std::string status() const;
    PHLMONITOR monitor;
    bool finished = false, failed = false, capturing = false;

  private:
    std::vector<Card> cards;
    Spring focus, openness;
    size_t origin = 0, anchor = 0;
    bool closing = false, committing = false, exitStarted = false;
    bool previousScanoutBlock = false;
    std::string previousSubmap;
    PHLWINDOWREF previousFocus;
    Time::steady_tp lastFrame;
    FlowRenderer renderer;
    SP<Render::ITexture> label;
    size_t labelIndex = static_cast<size_t>(-1);
    void refresh();
    void finish();
    Quad cardQuad(size_t index, bool reflection) const;
};
} // namespace Hyprflow

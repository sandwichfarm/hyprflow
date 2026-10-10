#include "Motion.hpp"
#include <cstdlib>
#include <iostream>
#include <limits>

using namespace Hyprflow;
void require(bool value, const char *message) {
    if (!value) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
bool near(double a, double b, double e = 1e-8) {
    return std::abs(a - b) < e;
}
void configurableSpacing() {
    for (const double spread : {0.0, .05, .18, .35, 1.0}) {
        for (const double boundary : {-1.0, 0.0, 1.0}) {
            const double h = .00001;
            const double left = (pose(boundary, spread).x - pose(boundary - h, spread).x) / h;
            const double right = (pose(boundary + h, spread).x - pose(boundary, spread).x) / h;
            require(near(left, right, .001), "custom spread keeps velocity continuous through selection");
        }
        for (int i = -4000; i <= 4000; ++i) {
            const double distance = i / 1000.;
            const auto p = pose(distance, spread), mirror = pose(-distance, spread);
            require(near(p.x, -mirror.x), "custom spread stays symmetric");
            require(pose(distance + .0001, spread).x >= p.x, "custom spread never reverses the card order");
            require(near(p.yaw, pose(distance).yaw) && near(p.z, pose(distance).z), "spread preserves perspective");
        }
    }
}
int main() {
    for (const auto monitor : {CardSize{1280, 720}, CardSize{720, 1280}, CardSize{960, 960}, CardSize{3440, 1440}}) {
        for (const double scale : {.1, .75, 1.0, 2.0}) {
            const auto size = cardSize(monitor.width, monitor.height, scale);
            require(near(size.width / size.height, monitor.width / monitor.height), "cards preserve native monitor aspect without matte");
            require(near(size.width, cardSide(monitor.width, monitor.height, scale)), "scale preserves horizontal footprint");
            for (const double progress : {0.0, .1, .5, .9, 1.0}) {
                const double width = std::lerp(monitor.width, size.width, progress);
                const double height = std::lerp(monitor.height, size.height, progress);
                require(near(width / height, monitor.width / monitor.height), "entry and exit retain source aspect at every step");
            }
            const auto top = project(pose(0), -.5, -.5 * size.height / size.width);
            const auto bottom = project(pose(0), .5, .5 * size.height / size.width);
            require(near((bottom.x - top.x) / (bottom.y - top.y), monitor.width / monitor.height), "rendered selected quad has native aspect");
        }
    }
    require(validSetting(0, 0, 1) && validSetting(1, 0, 1), "appearance ranges accept both endpoints");
    require(validSetting(64, 0, 64), "maximum blur radius accepted");
    for (const double invalid : {-1.0, 65.0, std::numeric_limits<double>::infinity(), std::numeric_limits<double>::quiet_NaN()})
        require(!validSetting(invalid, 0, 64), "invalid appearance values rejected");
    require(near(cardSide(1280, 720, 1.0), 417.6), "default workspace size preserves landscape geometry");
    require(near(cardSide(960, 960, 1.0), 364.8), "default workspace size preserves square geometry");
    require(near(cardSide(1280, 720, .75), 313.2), "workspace scale resizes the card");
    require(near(pose(1, .35).x, .84), "spread preserves the nearest cover position");
    require(near(pose(3, .35).x, 1.54), "spread changes the distance between inactive covers");
    configurableSpacing();
    auto center = pose(0);
    require(near(center.x, 0) && near(center.yaw, 0), "selected cover flat and centered");
    auto left = pose(-1), right = pose(1);
    require(left.yaw > 0 && right.yaw < 0, "outside edges face forward");
    const auto outer = project(left, -.5, .5), inner = project(left, .5, .5);
    require(near(2 * outer.y, 1.001263, .001), "reference outer edge height");
    require(near(2 * inner.y, .734609, .001), "reference inner edge height");
    require(near(-.5 - outer.x, .552, .01), "reference nearest visible width");
    for (int k = -6000; k <= 6000; ++k) {
        const double d = k / 1000.;
        auto a = pose(d), b = pose(-d);
        require(near(a.x, -b.x) && near(a.yaw, -b.yaw), "mirrored stack property");
        require(a.shade >= .77 && a.shade <= 1, "brightness bounds");
        require(pose(d + .0001).x > a.x, "continuous ordered travel");
        require(project(a, -.5, .5).w > 0 && project(a, .5, .5).w > 0, "valid projective depth");
    }
    for (double boundary : {-1., 0., 1.}) {
        const double h = .00001;
        const double l = (pose(boundary).x - pose(boundary - h).x) / h;
        const double r = (pose(boundary + h).x - pose(boundary).x) / h;
        require(near(l, r, .001), "no velocity seam in geometry");
    }
    Spring single{0, 0, 7}, frames = single;
    single.advance(.4);
    for (int i = 0; i < 144; ++i)
        frames.advance(.4 / 144);
    require(near(single.value, frames.value) && near(single.velocity, frames.velocity), "frame-rate independence");
    Spring step{0, 0, 1};
    step.advance(.195);
    require(near(step.value, .9, .002), "one-step 90 percent timing");
    const auto before = step;
    step.target = -1;
    require(step.value == before.value && step.velocity == before.velocity, "retarget preserves motion");
    step.advance(.00001);
    require(std::abs(step.value - before.value) < .001, "rapid reversal continuous");
    Spring open{0, 0, 1};
    for (int i = 0; i < 60; ++i) {
        open.advance(1. / 60);
        require(open.value >= 0 && open.value <= 1, "opening never overshoots");
    }
    require(open.settled(), "opening converges");
    std::array<Point, 4> corners;
    for (size_t i = 0; i < corners.size(); ++i) {
        const double u = (i % 2) - .5, v = (i / 2) - .5;
        auto projected = project(pose(.5), u, v);
        projected.x = 640 + 418 * projected.x;
        projected.y = 288 + 418 * projected.y;
        corners[i] = morph({(u + .5) * 1280, (v + .5) * 720, 1}, projected, .5);
    }
    require(near(corners[0].x * corners[0].w + corners[3].x * corners[3].w, corners[1].x * corners[1].w + corners[2].x * corners[2].w),
            "entry quad remains projective in x");
    require(near(corners[0].y * corners[0].w + corners[3].y * corners[3].w, corners[1].y * corners[1].w + corners[2].y * corners[2].w),
            "entry quad remains projective in y");
    std::cout << "PASS: geometry landmarks, 12001 symmetry/order/depth samples, timing, reversal, frame-rate independence\n";
}

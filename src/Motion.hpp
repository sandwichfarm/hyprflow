#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <numbers>

namespace Hyprflow {
// Closed-form critical damping: retargeting preserves position and velocity.
struct Spring {
    double value = 0, velocity = 0, target = 0;
    void advance(double seconds, double frequency = 20) {
        const double dt = std::max(0.0, seconds);
        const double delta = value - target;
        const double impulse = velocity + frequency * delta;
        const double decay = std::exp(-frequency * dt);
        value = target + (delta + impulse * dt) * decay;
        velocity = (velocity - frequency * impulse * dt) * decay;
    }
    bool settled(double tolerance = 0.0001) const {
        return std::abs(value - target) < tolerance && std::abs(velocity) < tolerance * 20;
    }
};

inline double smooth(double t) {
    t = std::clamp(t, 0.0, 1.0);
    return t * t * (3 - 2 * t);
}

struct Pose {
    double x, z, yaw, shade;
};

// Distances are in card heights; yaw sign puts the outside edges toward the viewer.
inline Pose pose(double distance) {
    const double a = std::abs(distance), t = std::min(1.0, a);
    const double s = smooth(t), sign = distance < 0 ? -1.0 : 1.0;
    const double x = a <= 1 ? 0.84 * s + 1.5 * (t * t * t - 2 * t * t + t) + 0.18 * (t * t * t - t * t) : 0.84 + 0.18 * (a - 1);
    return {sign * x, -0.45 * s, -sign * 65 * std::numbers::pi / 180 * s, 1 - 0.23 * s};
}

struct Point {
    double x, y, w;
};

inline Point morph(Point from, Point to, double progress) {
    const double w = std::lerp(from.w, to.w, progress);
    return {std::lerp(from.x * from.w, to.x * to.w, progress) / w, std::lerp(from.y * from.w, to.y * to.w, progress) / w, w};
}

// Homogeneous projection supplies clip w so the GPU interpolates UVs projectively.
inline Point project(const Pose &p, double u, double v) {
    const double z = p.z - u * std::sin(p.yaw);
    const double w = (2.5 - z) / 2.5;
    return {(p.x + u * std::cos(p.yaw)) / w, v / w, w};
}
} // namespace Hyprflow

#include "FlowRenderer.hpp"
#include <hyprland/src/render/OpenGL.hpp>
#include <hyprland/src/render/Renderer.hpp>
#include <GLES3/gl32.h>
#include <stdexcept>

namespace Hyprflow {
namespace {
const char *vertexSource = R"(#version 300 es
layout(location=0) in vec4 position;
layout(location=1) in vec2 texcoord;
out vec2 uv;
void main() { gl_Position = position; uv = texcoord; }
)";
const std::string nativeGradient{
#include <hyprland/src/render/shaders/gradient.glsl.inc>
};

// Reuse the compositor's Oklab interpolation and angular convention on our projective quads.
const std::string fragmentSource = std::string(R"(#version 300 es
precision highp float;
#define ALLOW_INCLUDES
#define CM_TRANSFER_FUNCTION_GAMMA22 2
vec3 fromLinearRGB(vec3 color, int transferFunction) {
    return pow(max(color, vec3(0.0)), vec3(1.0 / 2.2));
}
)") + nativeGradient + R"(
uniform sampler2D image;
uniform vec4 appearance;
uniform vec2 fraction;
uniform int blurPass;
uniform vec2 blurStep;
uniform float reflectionOpacity;
uniform bool backdrop;
uniform bool workspaceOverlay;
uniform vec4 tint;
uniform vec4 borderColors[10];
uniform int borderColorCount;
uniform float borderAngle;
uniform vec2 borderThickness;
in vec2 uv;
out vec4 color;
void main() {
    if (blurPass > 0) {
        vec4 sum = vec4(0);
        float total = 0.0;
        if (blurPass == 1) {
            // Prefilter the downsample footprint before blurring, avoiding text aliasing.
            for (int y = 0; y < 4; ++y) {
                for (int x = 0; x < 4; ++x)
                    sum += texture(image, uv + (vec2(float(x), float(y)) - 1.5) * blurStep);
            }
            total = 16.0;
        } else {
            for (int i = -4; i <= 4; ++i) {
                float weight = exp(-float(i * i) / 8.0);
                sum += texture(image, uv + float(i) * blurStep) * weight;
                total += weight;
            }
        }
        color = sum / total;
        return;
    }
    if (backdrop) {
        vec4 base = vec4(0, 0, 0, 1);
        if (workspaceOverlay) {
            base = texture(image, uv);
        }
        color = vec4(mix(base.rgb, tint.rgb, tint.a), 1.0);
        return;
    }
    vec2 sampleUV = (uv - .5) / fraction + .5;
    vec4 texel = vec4(0.015, 0.015, 0.015, 1.0);
    if (all(greaterThanEqual(sampleUV, vec2(0))) && all(lessThanEqual(sampleUV, vec2(1))))
        texel = texture(image, sampleUV);
    if (borderColorCount > 0 && all(greaterThan(borderThickness, vec2(0)))) {
        vec2 distanceToEdge = min(uv, 1.0 - uv);
        vec2 antialias = max(fwidth(uv) * .5, vec2(.000001));
        vec2 stroke = 1.0 - smoothstep(borderThickness - antialias, borderThickness + antialias, distanceToEdge);
        vec4 border = okLabAToSrgb(getOkColorForCoordArray1(uv, borderColorCount, borderColors, borderAngle));
        float coverage = max(stroke.x, stroke.y);
        texel = vec4(border.rgb * border.a, border.a) * coverage + texel * (1.0 - border.a * coverage);
    }
    float alpha = appearance.x;
    if (appearance.z > .5)
        alpha *= reflectionOpacity * pow(smoothstep(.55, 1.0, uv.y), 1.5);
    float light = appearance.y + .22 * (1.0 - appearance.y) * appearance.w * (2.0 * uv.x - 1.0);
    color = vec4(texel.rgb * light * alpha, texel.a * alpha);
}
)";

GLuint compile(GLenum type, const char *source) {
    const GLuint shader = glCreateShader(type);
    glShaderSource(shader, 1, &source, nullptr);
    glCompileShader(shader);
    GLint good = 0;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &good);
    if (!good) {
        char error[1024]{};
        glGetShaderInfoLog(shader, sizeof(error), nullptr, error);
        glDeleteShader(shader);
        throw std::runtime_error(std::string("hyprflow shader: ") + error);
    }
    return shader;
}

// Do not leave raw GL state inconsistent with Hyprland's cached renderer state.
struct GLState {
    GLint program, vao, buffer, active, texture, sampler, drawFramebuffer, readFramebuffer, viewport[4], blendSrcRGB, blendDstRGB, blendSrcA,
        blendDstA;
    GLboolean blend, scissor, depth, cull, stencil;
    GLfloat clear[4];
    GLState() {
        glGetIntegerv(GL_CURRENT_PROGRAM, &program);
        glGetIntegerv(GL_VERTEX_ARRAY_BINDING, &vao);
        glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &buffer);
        glGetIntegerv(GL_ACTIVE_TEXTURE, &active);
        glActiveTexture(GL_TEXTURE0);
        glGetIntegerv(GL_TEXTURE_BINDING_2D, &texture);
        glGetIntegerv(GL_SAMPLER_BINDING, &sampler);
        glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &drawFramebuffer);
        glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING, &readFramebuffer);
        glGetIntegerv(GL_VIEWPORT, viewport);
        glGetFloatv(GL_COLOR_CLEAR_VALUE, clear);
        glGetIntegerv(GL_BLEND_SRC_RGB, &blendSrcRGB);
        glGetIntegerv(GL_BLEND_DST_RGB, &blendDstRGB);
        glGetIntegerv(GL_BLEND_SRC_ALPHA, &blendSrcA);
        glGetIntegerv(GL_BLEND_DST_ALPHA, &blendDstA);
        blend = glIsEnabled(GL_BLEND);
        scissor = glIsEnabled(GL_SCISSOR_TEST);
        depth = glIsEnabled(GL_DEPTH_TEST);
        cull = glIsEnabled(GL_CULL_FACE);
        stencil = glIsEnabled(GL_STENCIL_TEST);
    }
    ~GLState() {
        glUseProgram(program);
        glBindVertexArray(vao);
        glBindBuffer(GL_ARRAY_BUFFER, buffer);
        glBindTexture(GL_TEXTURE_2D, texture);
        glBindSampler(0, sampler);
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, drawFramebuffer);
        glBindFramebuffer(GL_READ_FRAMEBUFFER, readFramebuffer);
        glActiveTexture(active);
        glViewport(viewport[0], viewport[1], viewport[2], viewport[3]);
        glClearColor(clear[0], clear[1], clear[2], clear[3]);
        glBlendFuncSeparate(blendSrcRGB, blendDstRGB, blendSrcA, blendDstA);
        restore(GL_BLEND, blend);
        restore(GL_SCISSOR_TEST, scissor);
        restore(GL_DEPTH_TEST, depth);
        restore(GL_CULL_FACE, cull);
        restore(GL_STENCIL_TEST, stencil);
    }
    static void restore(GLenum cap, GLboolean enabled) {
        enabled ? glEnable(cap) : glDisable(cap);
    }
};
} // namespace

void FlowRenderer::initialize() {
    if (program)
        return;
    GLuint vertex = compile(GL_VERTEX_SHADER, vertexSource), fragment = 0;
    try {
        fragment = compile(GL_FRAGMENT_SHADER, fragmentSource.c_str());
    } catch (...) {
        glDeleteShader(vertex);
        throw;
    }
    program = glCreateProgram();
    glAttachShader(program, vertex);
    glAttachShader(program, fragment);
    glLinkProgram(program);
    glDeleteShader(vertex);
    glDeleteShader(fragment);
    GLint good = 0;
    glGetProgramiv(program, GL_LINK_STATUS, &good);
    if (!good) {
        glDeleteProgram(program);
        program = 0;
        throw std::runtime_error("hyprflow shader link failed");
    }
    glGenVertexArrays(1, &vao);
    glGenBuffers(1, &buffer);
    glGenSamplers(1, &blurSampler);
    glSamplerParameteri(blurSampler, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glSamplerParameteri(blurSampler, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glSamplerParameteri(blurSampler, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glSamplerParameteri(blurSampler, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
}

FlowRenderer::~FlowRenderer() {
    if (!program)
        return;
    Render::GL::g_pHyprOpenGL->makeEGLCurrent();
    blurBuffers = {};
    glDeleteSamplers(1, &blurSampler);
    glDeleteProgram(program);
    glDeleteBuffers(1, &buffer);
    glDeleteVertexArrays(1, &vao);
}

GLuint FlowRenderer::blurredTexture(const Quad &quad, int width, int height) {
    const double downsample = std::max(1.0, quad.blurRadius / 4.0);
    const int w = std::max(1, static_cast<int>(std::ceil(width / downsample)));
    const int h = std::max(1, static_cast<int>(std::ceil(height / downsample)));
    for (auto &framebuffer : blurBuffers) {
        if (!framebuffer)
            framebuffer = g_pHyprRenderer->createFB("hyprflow backdrop blur");
        if (!framebuffer || !framebuffer->alloc(w, h, DRM_FORMAT_ARGB8888))
            throw std::runtime_error("hyprflow: backdrop blur allocation failed");
        const auto texture = framebuffer->getTexture();
        texture->setTexParameter(GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        texture->setTexParameter(GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        texture->setTexParameter(GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        texture->setTexParameter(GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    }
    const std::array<float, 24> fullscreen = {-1, -1, 0, 1, 0, 0, 1, -1, 0, 1, 1, 0, -1, 1, 0, 1, 0, 1, 1, 1, 0, 1, 1, 1};
    glBufferData(GL_ARRAY_BUFFER, sizeof(fullscreen), fullscreen.data(), GL_STREAM_DRAW);
    glViewport(0, 0, w, h);
    glDisable(GL_BLEND);
    glBindSampler(0, blurSampler);
    GLuint input = quad.texture->m_texID;
    for (int pass = 0; pass < 3; ++pass) {
        blurBuffers[pass % 2]->bind();
        glBindTexture(GL_TEXTURE_2D, input);
        glUniform1i(glGetUniformLocation(program, "blurPass"), pass + 1);
        if (pass == 0)
            glUniform2f(glGetUniformLocation(program, "blurStep"), 1.F / (4 * w), 1.F / (4 * h));
        else
            glUniform2f(glGetUniformLocation(program, "blurStep"), pass == 1 ? quad.blurRadius / (4 * width) : 0,
                        pass == 2 ? quad.blurRadius / (4 * height) : 0);
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
        input = blurBuffers[pass % 2]->getTexture()->m_texID;
    }
    glBindSampler(0, 0);
    glUniform1i(glGetUniformLocation(program, "blurPass"), 0);
    return input;
}

void FlowRenderer::draw(const std::vector<Quad> &quads, int width, int height) {
    GLState guard;
    initialize();
    glDisable(GL_SCISSOR_TEST);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    glDisable(GL_STENCIL_TEST);
    glViewport(0, 0, width, height);
    glEnable(GL_BLEND);
    glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA);
    glUseProgram(program);
    glBindVertexArray(vao);
    glBindBuffer(GL_ARRAY_BUFFER, buffer);
    glEnableVertexAttribArray(0);
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(0, 4, GL_FLOAT, GL_FALSE, 6 * sizeof(float), nullptr);
    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 6 * sizeof(float), reinterpret_cast<void *>(4 * sizeof(float)));
    glUniform1i(glGetUniformLocation(program, "image"), 0);
    glUniform1i(glGetUniformLocation(program, "blurPass"), 0);
    GLuint backgroundTexture = 0;
    for (const auto &quad : quads) {
        if (quad.backdrop && quad.workspaceOverlay && quad.blurRadius > 0 && quad.texture) {
            backgroundTexture = blurredTexture(quad, width, height);
            glBindFramebuffer(GL_DRAW_FRAMEBUFFER, guard.drawFramebuffer);
            glBindFramebuffer(GL_READ_FRAMEBUFFER, guard.readFramebuffer);
            glViewport(0, 0, width, height);
            glEnable(GL_BLEND);
            break;
        }
    }
    glClearColor(0, 0, 0, 1);
    glClear(GL_COLOR_BUFFER_BIT);
    const std::array<std::array<float, 2>, 4> uv = {{{0, 0}, {1, 0}, {0, 1}, {1, 1}}};
    for (const auto &quad : quads) {
        if (!quad.texture)
            continue;
        std::array<float, 24> vertices{};
        for (size_t i = 0; i < 4; ++i) {
            const auto &p = quad.points[i];
            vertices[i * 6] = (2 * p.x / width - 1) * p.w;
            vertices[i * 6 + 1] = (2 * p.y / height - 1) * p.w;
            vertices[i * 6 + 2] = 0;
            vertices[i * 6 + 3] = p.w;
            vertices[i * 6 + 4] = uv[i][0];
            vertices[i * 6 + 5] = uv[i][1];
        }
        glBindTexture(GL_TEXTURE_2D, quad.backdrop && backgroundTexture ? backgroundTexture : quad.texture->m_texID);
        glUniform1i(glGetUniformLocation(program, "backdrop"), quad.backdrop);
        glUniform1i(glGetUniformLocation(program, "workspaceOverlay"), quad.workspaceOverlay);
        glUniform4fv(glGetUniformLocation(program, "tint"), 1, quad.tint.data());
        glUniform1f(glGetUniformLocation(program, "reflectionOpacity"), quad.reflectionOpacity);
        glUniform4f(glGetUniformLocation(program, "appearance"), quad.opacity, quad.shade, quad.reflection, quad.lightDirection);
        glUniform2f(glGetUniformLocation(program, "fraction"), quad.imageWidth, quad.imageHeight);
        glUniform1i(glGetUniformLocation(program, "borderColorCount"), quad.borderColorCount);
        glUniform2fv(glGetUniformLocation(program, "borderThickness"), 1, quad.borderThickness.data());
        glUniform1f(glGetUniformLocation(program, "borderAngle"), quad.borderAngle);
        if (quad.borderColorCount > 0)
            glUniform4fv(glGetUniformLocation(program, "borderColors"), quad.borderColorCount, quad.borderColors.data());
        glBufferData(GL_ARRAY_BUFFER, sizeof(vertices), vertices.data(), GL_STREAM_DRAW);
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    }
}
} // namespace Hyprflow

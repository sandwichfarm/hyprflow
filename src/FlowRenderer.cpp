#include "FlowRenderer.hpp"
#include <hyprland/src/render/OpenGL.hpp>
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
const char *fragmentSource = R"(#version 300 es
precision highp float;
uniform sampler2D image;
uniform vec4 appearance;
uniform vec2 fraction;
in vec2 uv;
out vec4 color;
void main() {
    vec2 sampleUV = (uv - .5) / fraction + .5;
    vec4 texel = vec4(0.015, 0.015, 0.015, 1.0);
    if (all(greaterThanEqual(sampleUV, vec2(0))) && all(lessThanEqual(sampleUV, vec2(1))))
        texel = texture(image, sampleUV);
    float alpha = appearance.x;
    if (appearance.z > .5)
        alpha *= .34 * pow(smoothstep(.55, 1.0, uv.y), 1.5);
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
    GLint program, vao, buffer, active, texture, viewport[4], blendSrcRGB, blendDstRGB, blendSrcA, blendDstA;
    GLboolean blend, scissor, depth, cull, stencil;
    GLfloat clear[4];
    GLState() {
        glGetIntegerv(GL_CURRENT_PROGRAM, &program);
        glGetIntegerv(GL_VERTEX_ARRAY_BINDING, &vao);
        glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &buffer);
        glGetIntegerv(GL_ACTIVE_TEXTURE, &active);
        glActiveTexture(GL_TEXTURE0);
        glGetIntegerv(GL_TEXTURE_BINDING_2D, &texture);
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
        fragment = compile(GL_FRAGMENT_SHADER, fragmentSource);
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
}

FlowRenderer::~FlowRenderer() {
    if (!program)
        return;
    Render::GL::g_pHyprOpenGL->makeEGLCurrent();
    glDeleteProgram(program);
    glDeleteBuffers(1, &buffer);
    glDeleteVertexArrays(1, &vao);
}

void FlowRenderer::draw(const std::vector<Quad> &quads, int width, int height) {
    GLState guard;
    initialize();
    glDisable(GL_SCISSOR_TEST);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    glDisable(GL_STENCIL_TEST);
    glViewport(0, 0, width, height);
    glClearColor(0, 0, 0, 1);
    glClear(GL_COLOR_BUFFER_BIT);
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
        glBindTexture(GL_TEXTURE_2D, quad.texture->m_texID);
        glUniform4f(glGetUniformLocation(program, "appearance"), quad.opacity, quad.shade, quad.reflection, quad.lightDirection);
        glUniform2f(glGetUniformLocation(program, "fraction"), quad.imageWidth, quad.imageHeight);
        glBufferData(GL_ARRAY_BUFFER, sizeof(vertices), vertices.data(), GL_STREAM_DRAW);
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    }
}
} // namespace Hyprflow

#include "FlowRenderer.hpp"
#include <hyprland/src/render/VKRenderer.hpp>
#include <hyprland/src/render/vulkan/Shader.hpp>
#include <hyprland/src/render/vulkan/utils.hpp>
#include <cstring>
#include <stdexcept>

namespace Hyprflow {
namespace {
using namespace Render::VK;

const std::string dataBlock = R"(
layout(std140, set=0, binding=1) uniform Data {
    vec4 positions[4];
    vec4 appearance;
    vec4 fractionBorder;
    vec4 tint;
    vec4 borderColors[10];
    vec4 effects;
    ivec4 flags;
};
#define fraction fractionBorder.xy
#define borderThickness fractionBorder.zw
#define borderAngle effects.x
#define reflectionOpacity effects.y
#define borderColorCount flags.z
)";
const std::string vertexSource = std::string("#version 450\n") + dataBlock + R"(
layout(location=0) out vec2 uv;
void main() {
    const int order[4] = int[4](0, 1, 3, 2);
    const vec2 coords[4] = vec2[4](vec2(0,0), vec2(1,0), vec2(0,1), vec2(1,1));
    int index = order[gl_VertexIndex];
    gl_Position = positions[index];
    uv = coords[index];
}
)";
const std::string fragmentSource = std::string("#version 450\n") + dataBlock + R"(
layout(set=0, binding=0) uniform sampler2D image;
layout(location=0) in vec2 uv;
layout(location=0) out vec4 color;
#define CM_TRANSFER_FUNCTION_GAMMA22 2
vec3 fromLinearRGB(vec3 color, int transferFunction) {
    return pow(max(color, vec3(0.0)), vec3(1.0 / 2.2));
}
vec4 okLabAToSrgb(vec4 lab) {
    float l = pow(lab[0] + lab[1] * 0.3963377774 + lab[2] * 0.2158037573, 3.0);
    float m = pow(lab[0] + lab[1] * (-0.1055613458) + lab[2] * (-0.0638541728), 3.0);
    float s = pow(lab[0] + lab[1] * (-0.0894841775) + lab[2] * (-1.2914855480), 3.0);

    return vec4(fromLinearRGB(vec3(l * 4.0767416621 + m * -3.3077115913 + s * 0.2309699292,
                                   l * (-1.2684380046) + m * 2.6097574011 + s * (-0.3413193965),
                                   l * (-0.0041960863) + m * (-0.7034186147) + s * 1.7076147010),
                              CM_TRANSFER_FUNCTION_GAMMA22),
                lab[3]);
}

vec4 getOkColorForCoordArray1(vec2 normalizedCoord, int gradientLength, vec4 gradient[10], float angle) {
    if (gradientLength < 2)
        return gradient[0];

    float finalAng = 0.0;

    if (angle > 4.71 /* 270 deg */) {
        normalizedCoord[1] = 1.0 - normalizedCoord[1];
        finalAng           = 6.28 - angle;
    } else if (angle > 3.14 /* 180 deg */) {
        normalizedCoord[0] = 1.0 - normalizedCoord[0];
        normalizedCoord[1] = 1.0 - normalizedCoord[1];
        finalAng           = angle - 3.14;
    } else if (angle > 1.57 /* 90 deg */) {
        normalizedCoord[0] = 1.0 - normalizedCoord[0];
        finalAng           = 3.14 - angle;
    } else {
        finalAng = angle;
    }

    float sine = sin(finalAng);

    float progress = (normalizedCoord[1] * sine + normalizedCoord[0] * (1.0 - sine)) * float(gradientLength - 1);
    int   bottom   = min(int(floor(progress)), gradientLength - 1);
    int   top      = min(bottom + 1, gradientLength - 1);

    return gradient[top] * (progress - float(bottom)) + gradient[bottom] * (float(top) - progress);
}


void main() {
    if (flags.x != 0) {
        vec4 base = vec4(0, 0, 0, 1);
        if (flags.y != 0) {
            if (effects.z > 0.0) {
                // Pair adjacent texels with bilinear filtering. Unlike a sparse
                // radius-scaled grid, every texel in the Gaussian footprint contributes.
                vec2 texel = 1.0 / vec2(textureSize(image, 0));
                int radius = int(ceil(effects.z));
                float sigma = max(effects.z * 0.5, 0.01);
                float divisor = 2.0 * sigma * sigma;
                base = vec4(0);
                float total = 0.0;
                for (int y = -radius; y <= radius; y += 2) {
                    float y0 = exp(-float(y * y) / divisor);
                    float y1 = y < radius ? exp(-float((y + 1) * (y + 1)) / divisor) : 0.0;
                    float wy = y0 + y1;
                    if (wy < 0.0000001)
                        continue;
                    float offsetY = float(y) + y1 / wy;
                    for (int x = -radius; x <= radius; x += 2) {
                        float x0 = exp(-float(x * x) / divisor);
                        float x1 = x < radius ? exp(-float((x + 1) * (x + 1)) / divisor) : 0.0;
                        float wx = x0 + x1;
                        if (wx < 0.0000001)
                            continue;
                        float offsetX = float(x) + x1 / wx;
                        float weight = wx * wy;
                        base += texture(image, uv + vec2(offsetX, offsetY) * texel) * weight;
                        total += weight;
                    }
                }
                base /= total;
            } else
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

void require(VkResult result, const char *operation) {
    if (result != VK_SUCCESS)
        throw std::runtime_error(std::string("hyprflow Vulkan: ") + operation);
}

// Native renderer caches its bound pipeline. Restore the binding without changing that cache.
struct PipelineMember {
    using type = WP<CVkPipeline> CHyprVKRenderer::*;
    friend type pipelineMember(PipelineMember);
};
template <typename Tag, typename Tag::type Member> struct Access {
    friend typename Tag::type pipelineMember(Tag) {
        return Member;
    }
};
template struct Access<PipelineMember, &CHyprVKRenderer::m_currentPipeline>;

struct PipelineGuard {
    VkCommandBuffer command;
    WP<CVkPipeline> previous;
    ~PipelineGuard() {
        if (previous)
            vkCmdBindPipeline(command, VK_PIPELINE_BIND_POINT_GRAPHICS, previous->vk());
    }
};

struct alignas(16) DrawData {
    std::array<std::array<float, 4>, 4> positions{};
    std::array<float, 4> appearance{}, fractionBorder{}, tint{};
    std::array<float, 40> colors{};
    std::array<float, 4> effects{};
    std::array<int, 4> flags{};
};

struct FrameData {
    VkDevice device = VK_NULL_HANDLE;
    VkBuffer buffer = VK_NULL_HANDLE;
    VkDeviceMemory memory = VK_NULL_HANDLE;
    VkDescriptorPool pool = VK_NULL_HANDLE;
    void *mapping = nullptr;
    WP<CHyprVkCommandBuffer> command;
    uint64_t recordedAfterPoint = 0;
    ~FrameData() {
        if (pool)
            vkDestroyDescriptorPool(device, pool, nullptr);
        if (mapping)
            vkUnmapMemory(device, memory);
        if (buffer)
            vkDestroyBuffer(device, buffer, nullptr);
        if (memory)
            vkFreeMemory(device, memory, nullptr);
    }
};
} // namespace

struct FlowRenderer::VulkanState {
    VkDevice device = g_pHyprVulkan->vkDevice();
    VkDescriptorSetLayout descriptorLayout = VK_NULL_HANDLE;
    VkPipelineLayout layout = VK_NULL_HANDLE;
    VkPipeline pipeline = VK_NULL_HANDLE;
    VkSampler sampler = VK_NULL_HANDLE;
    VkFormat format = VK_FORMAT_UNDEFINED;
    std::vector<std::unique_ptr<FrameData>> frames;
    SP<CVkShader> vertex, fragment;

    void initialize() {
        VkSamplerCreateInfo samplerInfo{.sType = VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO,
                                        .magFilter = VK_FILTER_LINEAR,
                                        .minFilter = VK_FILTER_LINEAR,
                                        .addressModeU = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
                                        .addressModeV = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
                                        .addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE};
        require(vkCreateSampler(device, &samplerInfo, nullptr, &sampler), "sampler allocation");
        VkDescriptorSetLayoutBinding bindings[2] = {{.binding = 0,
                                                     .descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,
                                                     .descriptorCount = 1,
                                                     .stageFlags = VK_SHADER_STAGE_FRAGMENT_BIT},
                                                    {.binding = 1,
                                                     .descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,
                                                     .descriptorCount = 1,
                                                     .stageFlags = VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT}};
        VkDescriptorSetLayoutCreateInfo descriptorInfo{
            .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO, .bindingCount = 2, .pBindings = bindings};
        require(vkCreateDescriptorSetLayout(device, &descriptorInfo, nullptr, &descriptorLayout), "descriptor layout allocation");
        VkPipelineLayoutCreateInfo layoutInfo{
            .sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO, .setLayoutCount = 1, .pSetLayouts = &descriptorLayout};
        require(vkCreatePipelineLayout(device, &layoutInfo, nullptr, &layout), "pipeline layout allocation");
        vertex = makeShared<CVkShader>(g_pHyprVulkan->device(), vertexSource, 0, SH_VERT, "Hyprflow projective vertex");
        fragment = makeShared<CVkShader>(g_pHyprVulkan->device(), fragmentSource, 0, SH_FRAG, "Hyprflow appearance fragment");
    }
    ~VulkanState() {
        vkDeviceWaitIdle(device);
        frames.clear();
        if (pipeline)
            vkDestroyPipeline(device, pipeline, nullptr);
        if (layout)
            vkDestroyPipelineLayout(device, layout, nullptr);
        if (descriptorLayout)
            vkDestroyDescriptorSetLayout(device, descriptorLayout, nullptr);
        if (sampler)
            vkDestroySampler(device, sampler, nullptr);
    }

    void ensurePipeline(VkFormat target) {
        if (pipeline && target == format)
            return;
        if (pipeline) {
            require(vkDeviceWaitIdle(device), "wait before format change");
            vkDestroyPipeline(device, pipeline, nullptr);
            pipeline = VK_NULL_HANDLE;
        }
        VkPipelineShaderStageCreateInfo stages[2] = {{.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
                                                      .stage = VK_SHADER_STAGE_VERTEX_BIT,
                                                      .module = vertex->module(),
                                                      .pName = "main"},
                                                     {.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
                                                      .stage = VK_SHADER_STAGE_FRAGMENT_BIT,
                                                      .module = fragment->module(),
                                                      .pName = "main"}};
        VkPipelineVertexInputStateCreateInfo vertexInfo{.sType = VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
        VkPipelineInputAssemblyStateCreateInfo assembly{.sType = VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO,
                                                        .topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_FAN};
        VkPipelineViewportStateCreateInfo viewport{
            .sType = VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO, .viewportCount = 1, .scissorCount = 1};
        VkPipelineRasterizationStateCreateInfo raster{.sType = VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO,
                                                      .polygonMode = VK_POLYGON_MODE_FILL,
                                                      .cullMode = VK_CULL_MODE_NONE,
                                                      .frontFace = VK_FRONT_FACE_COUNTER_CLOCKWISE,
                                                      .lineWidth = 1};
        VkPipelineMultisampleStateCreateInfo samples{.sType = VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO,
                                                     .rasterizationSamples = VK_SAMPLE_COUNT_1_BIT};
        VkPipelineColorBlendAttachmentState blendAttachment{.blendEnable = true,
                                                            .srcColorBlendFactor = VK_BLEND_FACTOR_ONE,
                                                            .dstColorBlendFactor = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA,
                                                            .colorBlendOp = VK_BLEND_OP_ADD,
                                                            .srcAlphaBlendFactor = VK_BLEND_FACTOR_ONE,
                                                            .dstAlphaBlendFactor = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA,
                                                            .alphaBlendOp = VK_BLEND_OP_ADD,
                                                            .colorWriteMask = VK_COLOR_COMPONENT_R_BIT | VK_COLOR_COMPONENT_G_BIT |
                                                                              VK_COLOR_COMPONENT_B_BIT | VK_COLOR_COMPONENT_A_BIT};
        VkPipelineColorBlendStateCreateInfo blend{
            .sType = VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO, .attachmentCount = 1, .pAttachments = &blendAttachment};
        VkDynamicState dynamics[2] = {VK_DYNAMIC_STATE_VIEWPORT, VK_DYNAMIC_STATE_SCISSOR};
        VkPipelineDynamicStateCreateInfo dynamic{
            .sType = VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO, .dynamicStateCount = 2, .pDynamicStates = dynamics};
        VkPipelineRenderingCreateInfo rendering{
            .sType = VK_STRUCTURE_TYPE_PIPELINE_RENDERING_CREATE_INFO, .colorAttachmentCount = 1, .pColorAttachmentFormats = &target};
        VkGraphicsPipelineCreateInfo info{.sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO,
                                          .pNext = &rendering,
                                          .stageCount = 2,
                                          .pStages = stages,
                                          .pVertexInputState = &vertexInfo,
                                          .pInputAssemblyState = &assembly,
                                          .pViewportState = &viewport,
                                          .pRasterizationState = &raster,
                                          .pMultisampleState = &samples,
                                          .pColorBlendState = &blend,
                                          .pDynamicState = &dynamic,
                                          .layout = layout};
        require(vkCreateGraphicsPipelines(device, VK_NULL_HANDLE, 1, &info, nullptr, &pipeline), "graphics pipeline allocation");
        format = target;
    }

    std::unique_ptr<FrameData> frame(size_t count, size_t stride) {
        auto result = std::make_unique<FrameData>();
        result->device = device;
        result->command = g_pHyprVulkan->renderCB();
        result->recordedAfterPoint = result->command->m_timelinePoint;
        VkBufferCreateInfo bufferInfo{.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
                                      .size = count * stride,
                                      .usage = VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT,
                                      .sharingMode = VK_SHARING_MODE_EXCLUSIVE};
        require(vkCreateBuffer(device, &bufferInfo, nullptr, &result->buffer), "uniform buffer allocation");
        VkMemoryRequirements memoryRequirements;
        vkGetBufferMemoryRequirements(device, result->buffer, &memoryRequirements);
        int type = findVkMemType(g_pHyprVulkan->device()->physicalDevice(),
                                 VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT, memoryRequirements.memoryTypeBits);
        if (type < 0)
            throw std::runtime_error("hyprflow Vulkan: no coherent uniform memory");
        VkMemoryAllocateInfo memoryInfo{.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
                                        .allocationSize = memoryRequirements.size,
                                        .memoryTypeIndex = static_cast<uint32_t>(type)};
        require(vkAllocateMemory(device, &memoryInfo, nullptr, &result->memory), "uniform memory allocation");
        require(vkBindBufferMemory(device, result->buffer, result->memory, 0), "uniform memory binding");
        require(vkMapMemory(device, result->memory, 0, VK_WHOLE_SIZE, 0, &result->mapping), "uniform mapping");
        VkDescriptorPoolSize sizes[2] = {{VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, static_cast<uint32_t>(count)},
                                         {VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, static_cast<uint32_t>(count)}};
        VkDescriptorPoolCreateInfo poolInfo{
            .sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO, .maxSets = static_cast<uint32_t>(count), .poolSizeCount = 2, .pPoolSizes = sizes};
        require(vkCreateDescriptorPool(device, &poolInfo, nullptr, &result->pool), "descriptor pool allocation");
        return result;
    }

    void draw(const std::vector<Quad> &quads, int width, int height) {
        if (quads.empty())
            return;
        const auto framebuffer = g_pHyprRenderer->m_renderData.currentFB;
        if (!framebuffer || width < 1 || height < 1 || framebuffer->m_size.x != width || framebuffer->m_size.y != height)
            throw std::runtime_error("hyprflow Vulkan: render target extent differs from the flow output");
        const auto cb = g_pHyprVulkan->renderCB();
        const uint64_t completedPoint = g_pHyprVulkan->device()->timelinePoint();
        std::erase_if(frames, [completedPoint](const auto &frame) {
            // busy() describes recording, not execution. end() publishes a later
            // submission point; retain descriptors until the GPU reaches that point.
            return frame->command && frame->command->m_timelinePoint > frame->recordedAfterPoint && frame->command->m_timelinePoint <= completedPoint;
        });
        auto *renderer = static_cast<CHyprVKRenderer *>(g_pHyprRenderer.get());
        const PipelineGuard pipelineGuard{cb->vk(), renderer->*pipelineMember(PipelineMember{})};
        const auto formatInfo = g_pHyprVulkan->device()->getFormat(framebuffer->m_drmFormat);
        if (!formatInfo)
            throw std::runtime_error("hyprflow Vulkan: unknown render target format");
        ensurePipeline(formatInfo->format.vkFormat);
        VkPhysicalDeviceProperties properties;
        vkGetPhysicalDeviceProperties(g_pHyprVulkan->device()->physicalDevice(), &properties);
        const size_t alignment = properties.limits.minUniformBufferOffsetAlignment;
        const size_t stride = (sizeof(DrawData) + alignment - 1) / alignment * alignment;
        // Keep allocations alive even if a later descriptor allocation fails after draws were recorded.
        frames.push_back(frame(quads.size(), stride));
        const auto &frameData = frames.back();
        VkViewport viewport{.width = static_cast<float>(width), .height = static_cast<float>(height), .maxDepth = 1};
        VkRect2D scissor{.extent = {static_cast<uint32_t>(width), static_cast<uint32_t>(height)}};
        vkCmdSetViewport(cb->vk(), 0, 1, &viewport);
        vkCmdSetScissor(cb->vk(), 0, 1, &scissor);
        VkClearAttachment clear{.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT, .colorAttachment = 0, .clearValue = {.color = {{0, 0, 0, 1}}}};
        VkClearRect clearRect{.rect = scissor, .layerCount = 1};
        vkCmdClearAttachments(cb->vk(), 1, &clear, 1, &clearRect);
        vkCmdBindPipeline(cb->vk(), VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);
        for (size_t index = 0; index < quads.size(); ++index) {
            const auto &quad = quads[index];
            if (!quad.texture)
                continue;
            const auto texture = dynamicPointerCast<CVKTexture>(quad.texture);
            if (!texture)
                throw std::runtime_error("hyprflow Vulkan: unexpected texture backend");
            cb->useTexture(texture);
            DrawData data;
            for (size_t i = 0; i < 4; ++i) {
                const auto &p = quad.points[i];
                data.positions[i] = {static_cast<float>((2 * p.x / width - 1) * p.w), static_cast<float>((2 * p.y / height - 1) * p.w), 0,
                                     static_cast<float>(p.w)};
            }
            data.appearance = {quad.opacity, quad.shade, static_cast<float>(quad.reflection), quad.lightDirection};
            data.fractionBorder = {quad.imageWidth, quad.imageHeight, quad.borderThickness[0], quad.borderThickness[1]};
            data.tint = quad.tint;
            data.colors = quad.borderColors;
            data.effects = {quad.borderAngle, quad.reflectionOpacity, quad.blurRadius, 0};
            data.flags = {quad.backdrop, quad.workspaceOverlay, quad.borderColorCount, 0};
            memcpy(static_cast<char *>(frameData->mapping) + index * stride, &data, sizeof(data));
            VkDescriptorSetAllocateInfo alloc{.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,
                                              .descriptorPool = frameData->pool,
                                              .descriptorSetCount = 1,
                                              .pSetLayouts = &descriptorLayout};
            VkDescriptorSet descriptor;
            require(vkAllocateDescriptorSets(device, &alloc, &descriptor), "draw descriptor allocation");
            VkDescriptorImageInfo imageInfo{
                .sampler = sampler, .imageView = texture->vkView(), .imageLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL};
            VkDescriptorBufferInfo bufferInfo{.buffer = frameData->buffer, .offset = index * stride, .range = sizeof(data)};
            VkWriteDescriptorSet writes[2] = {{.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
                                               .dstSet = descriptor,
                                               .dstBinding = 0,
                                               .descriptorCount = 1,
                                               .descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,
                                               .pImageInfo = &imageInfo},
                                              {.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
                                               .dstSet = descriptor,
                                               .dstBinding = 1,
                                               .descriptorCount = 1,
                                               .descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,
                                               .pBufferInfo = &bufferInfo}};
            vkUpdateDescriptorSets(device, 2, writes, 0, nullptr);
            vkCmdBindDescriptorSets(cb->vk(), VK_PIPELINE_BIND_POINT_GRAPHICS, layout, 0, 1, &descriptor, 0, nullptr);
            vkCmdDraw(cb->vk(), 4, 1, 0, 0);
        }
    }
};

FlowRenderer::~FlowRenderer() {
    delete vulkan;
}
void FlowRenderer::draw(const std::vector<Quad> &quads, int width, int height) {
    if (!vulkan) {
        auto next = std::make_unique<VulkanState>();
        next->initialize();
        vulkan = next.release();
    }
    vulkan->draw(quads, width, height);
}
} // namespace Hyprflow

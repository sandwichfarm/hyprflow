-- Load build/hyprflow.so with hyprctl before sourcing this file.
-- Hyprland 0.56.2 Lua configuration. Change these bindings to taste.
hl.config({ plugin = { hyprflow = {
    workspace_count = 9,
    workspace_scale = 1.0,
    workspace_spread = 0.18,
    border_width = 0,
    border_color = "rgba(ffffffff)",
    border_color_current = "",
    border_color_focus = "",
} } })

hl.bind("SUPER + Tab", function() hl.plugin.hyprflow.toggle() end)
hl.bind("SUPER + ALT + Left", function() hl.plugin.hyprflow.left() end, { repeating = true })
hl.bind("SUPER + ALT + Right", function() hl.plugin.hyprflow.right() end, { repeating = true })

-- Direct workspace bindings open the flow and animate to that workspace.
for index = 1, 9 do
    hl.bind("SUPER + ALT + " .. index, function() hl.plugin.hyprflow.jump(index) end)
end

-- Hyprflow enters this submap and restores the previous one on exit/unload.
hl.define_submap("hyprflow", function()
    hl.bind("Left", function() hl.plugin.hyprflow.left() end, { repeating = true })
    hl.bind("Right", function() hl.plugin.hyprflow.right() end, { repeating = true })
    hl.bind("SUPER + ALT + Left", function() hl.plugin.hyprflow.left() end, { repeating = true })
    hl.bind("SUPER + ALT + Right", function() hl.plugin.hyprflow.right() end, { repeating = true })
    hl.bind("Return", function() hl.plugin.hyprflow.accept() end)
    hl.bind("Escape", function() hl.plugin.hyprflow.cancel() end)
    hl.bind("SUPER + Tab", function() hl.plugin.hyprflow.toggle() end)
    for index = 1, 9 do
        hl.bind(tostring(index), function() hl.plugin.hyprflow.jump(index) end)
        hl.bind("SUPER + ALT + " .. index, function() hl.plugin.hyprflow.jump(index) end)
    end
    hl.bind("catchall", function() end)
end)

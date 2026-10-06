-- Isolated development compositor. Never source this into your daily session.
hl.monitor({ output = "", mode = "1280x720@60", position = "auto", scale = 1 })
hl.config({
    general = { gaps_in = 0, gaps_out = 0, border_size = 0 },
    decoration = { rounding = 0, shadow = { enabled = false }, blur = { enabled = false } },
    animations = { enabled = false },
    input = { follow_mouse = 0 },
    misc = {
        disable_hyprland_logo = true,
        disable_splash_rendering = true,
        disable_autoreload = true,
        disable_hyprland_guiutils_check = true,
    },
    debug = { disable_logs = false },
    ecosystem = { no_update_news = true, no_donation_nag = true },
})

for index = 1, 7 do
    hl.workspace_rule({ workspace = tostring(index), persistent = true })
    hl.bind("ALT + " .. index, hl.dsp.focus({ workspace = index }))
end

-- These callbacks resolve only when pressed, so startup works before a plugin build exists.
hl.bind("F10", function() hl.plugin.hyprflow.toggle() end)
hl.define_submap("hyprflow", function()
    hl.bind("F10", function() hl.plugin.hyprflow.toggle() end)
    hl.bind("Left", function() hl.plugin.hyprflow.left() end)
    hl.bind("Right", function() hl.plugin.hyprflow.right() end)
    hl.bind("Return", function() hl.plugin.hyprflow.accept() end)
    hl.bind("Escape", function() hl.plugin.hyprflow.cancel() end)
    for index = 1, 7 do
        hl.bind(tostring(index), function() hl.plugin.hyprflow.jump(index) end)
    end
    hl.bind("catchall", function() end)
end)

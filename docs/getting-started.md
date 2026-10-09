# Getting started

Hyprflow is a native Hyprland plugin. It presents your workspaces as a Cover Flow stack, with a selected cover and fading floor reflections.

## Install with hyprpm

The supported target is **Hyprland 0.56.2 with the OpenGL renderer**. Other compositor revisions and Vulkan are not qualified. Check your session with `hyprctl version`.

Use [Hyprland's plugin manager](https://wiki.hypr.land/Plugins/Using-Plugins/#hyprpm) from a terminal inside your Hyprland session:

```sh
hyprpm update
hyprpm add https://github.com/sandwichfarm/hyprflow
hyprpm enable hyprflow
hyprpm reload
```

Run these as your normal user, not with `sudo`. Hyprpm prepares matching Hyprland headers, downloads and builds Hyprflow, and manages the installed plugin. `hyprpm update` prepares the headers for a first install and updates any other plugins you already manage with hyprpm. No manual clone is needed.

Hyprpm builds from source, so install its build prerequisites (`git`, CMake, cpio, pkg-config, GCC/G++, and Make) and your distribution's Hyprland build dependencies first. Hyprflow additionally uses the development packages for Lua 5.4, EGL, GLES, and Pango/Cairo. The compiler must support C++23. A missing package is reported in the build output; see [troubleshooting](troubleshooting.md).

Confirm that installation and loading succeeded:

```sh
hyprpm list
hyprctl plugin list
```

The repository and plugin are both named `hyprflow`. The manifest builds `build/hyprflow.so`; hyprpm installs and loads its own managed copy. Check that `hyprflow` is enabled, has no build failure, and appears in the compositor's loaded-plugin list.

## Set up controls

Add this to your active `hyprland.lua` configuration. These callbacks resolve the plugin when a key is pressed, so the config can be read before hyprpm loads the plugin at startup.

```lua
-- If you already autostart hyprpm, keep just one startup entry.
hl.on("hyprland.start", function()
    hl.exec_cmd("hyprpm reload -n")
end)

hl.bind("SUPER + Tab", function() hl.plugin.hyprflow.toggle() end)
hl.define_submap("hyprflow", function()
    hl.bind("Left", function() hl.plugin.hyprflow.left() end, { repeating = true })
    hl.bind("Right", function() hl.plugin.hyprflow.right() end, { repeating = true })
    hl.bind("Return", function() hl.plugin.hyprflow.accept() end)
    hl.bind("Escape", function() hl.plugin.hyprflow.cancel() end)
    hl.bind("SUPER + Tab", function() hl.plugin.hyprflow.toggle() end)
    for index = 1, 9 do
        hl.bind(tostring(index), function() hl.plugin.hyprflow.jump(index) end)
    end
    hl.bind("catchall", function() end)
end)
```

Reload the configuration with `hyprctl reload` and check `hyprctl configerrors`. Press **Super + Tab**, then **Left / Right** or **1–9**. **Return** activates the selection; **Escape** returns to your original workspace. Keep the modal submap and its `catchall` binding so unrelated keys do not reach applications underneath.

The startup callback loads enabled plugins on future logins. The earlier `hyprpm reload` command loads them into your current session immediately. This uses Hyprland's [Lua startup event](https://wiki.hypr.land/Configuring/Advanced-and-Cool/Expanding-functionality/#events).

For all default bindings and appearance options, save the [full configuration file](https://raw.githubusercontent.com/sandwichfarm/hyprflow/main/config/hyprflow.lua) as `hyprflow.lua` beside your main config. Keep the startup callback above, and replace its binding block with:

```lua
local config_home = os.getenv("XDG_CONFIG_HOME") or (os.getenv("HOME") .. "/.config")
if hl.plugin.hyprflow then
    dofile(config_home .. "/hypr/hyprflow.lua")
end
```

The guard defers plugin-specific settings until the plugin is loaded. Hyprland rereads the configuration after loading a plugin. See [configuration and controls](configuration.md) for customization.

## Update or remove

After updating Hyprland, restart into the installed version before loading rebuilt plugins. Then update and reload:

```sh
hyprpm update
hyprpm reload
```

Hyprland plugins require matching headers and dependency ABI. Hyprpm's header management does not make unsupported Hyprland versions compatible with Hyprflow. If a build fails, keep the error output and check the supported version before proceeding.

To disable Hyprflow, remove its bindings/config include and run:

```sh
hyprpm disable hyprflow
hyprpm reload
```

To remove the repository as well:

```sh
hyprpm remove https://github.com/sandwichfarm/hyprflow
```

Keep the startup `hyprpm reload` callback if you use it for other plugins.

## Build from source (development)

Manual builds are for development or an isolated test session. Install a C++23 compiler, Make, pkg-config, matching Hyprland development headers and their dependencies, Lua 5.4, EGL, GLES, and Pango/Cairo development packages. The plugin checks the full API hash at load time. Make does not download or vendor dependencies.

```sh
git clone https://github.com/sandwichfarm/hyprflow.git
cd hyprflow
pkg-config --modversion hyprland
make -j2
make test
```

The output is `build/hyprflow.so`.

## Try an isolated session

From an existing Wayland session, use the repository helper to create a nested compositor. It needs `kitty` for fixtures and `grim` for screenshots; recordings also need `wf-recorder`.

```sh
session_dir=$(python3 scripts/nested-session.py start | python3 -c 'import json,sys; print(json.load(sys.stdin)["directory"])')
python3 scripts/nested-session.py place "$session_dir"
python3 scripts/nested-session.py fixtures "$session_dir"
python3 scripts/nested-session.py ctl "$session_dir" plugin load "$PWD/build/hyprflow.so"
```

Focus the nested window and press **F10**, then **Left / Right** or **1–7**. **Return** activates the selection; **Escape** returns to the original workspace.

```sh
python3 scripts/nested-session.py ctl "$session_dir" repl 'return hl.plugin.hyprflow.status()'
python3 scripts/nested-session.py stop "$session_dir"
```

The helper targets only the nested instance. Stopping restores the owned window placement and exits the recorded compositor process.

## Load a manual build

For a manual build only; hyprpm users should use `hyprpm reload`. Unload any already loaded Hyprflow copy before switching installation methods. From the repository directory:

```sh
hyprctl plugin load "$PWD/build/hyprflow.so"
```

Then source the supplied `config/hyprflow.lua` in your Hyprland Lua configuration, using an absolute path:

```lua
dofile("/absolute/path/to/hyprflow/config/hyprflow.lua")
```

The plugin must be loaded before the configuration is evaluated. **Super + Tab** opens the flow. See [configuration and controls](configuration.md) for all bindings and actions.

::: warning Rebuilding
Unload the plugin before overwriting its loaded shared library. After a compositor upgrade, rebuild against the new headers before loading again.
:::

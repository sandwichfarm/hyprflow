# Getting started

Hyprflow is a native Hyprland plugin. It presents your workspaces as a Cover Flow stack, with a selected cover and fading floor reflections.

## Requirements

The verified target is **Hyprland 0.56.2 with the OpenGL renderer**. Other compositor revisions and Vulkan are not qualified. Build against the development headers matching the compositor that will load the plugin; the full API hash is checked at load time.

Install a C++23 compiler, Make, pkg-config, Hyprland development headers and their dependencies, Lua 5.4, EGL, GLES, and Pango/Cairo development packages through your distribution. No plugin dependencies are downloaded or vendored by Make.

## Build from source

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

## Load in your session

From the repository directory:

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

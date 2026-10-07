# Configuration & controls

The [default Lua configuration](https://github.com/sandwichfarm/hyprflow/blob/main/config/hyprflow.lua) defines independent actions and a modal `hyprflow` submap. Load the plugin before sourcing it.

## Workspace count

```lua
hl.config({ plugin = { hyprflow = { workspace_count = 9 } } })
```

`workspace_count` defaults to **9**, with an allowed range of **1–32**. Numeric cards do not create real workspaces until accepted. Existing workspaces on the focused monitor, including named workspaces, are also included. Workspaces on other monitors and special workspaces are excluded from navigation; an active special overlay is included in the original card.

## Default bindings

| Binding | Action |
| --- | --- |
| Super + Tab | Open; toggle reverses entry or closing |
| Super + Alt + Left / Right | Open and move selection |
| Super + Alt + 1–9 | Open and jump to a workspace |
| Left / Right while open | Move selection |
| 1–9 while open | Animate to that workspace |
| Return | Expand and activate selection |
| Escape | Return to original workspace |

Selection is separate from activation. Jumps travel through intermediate covers and leave the flow open. Invalid targets return an error, and navigation clamps at the ends.

## Lua actions and dispatchers

| Lua action | Dispatcher | Effect |
| --- | --- | --- |
| `hl.plugin.hyprflow.toggle()` | `hyprflow:toggle` | Open or reverse the transition |
| `hl.plugin.hyprflow.left()` | `hyprflow:left` | Move one card left |
| `hl.plugin.hyprflow.right()` | `hyprflow:right` | Move one card right |
| `hl.plugin.hyprflow.jump(id_or_name)` | `hyprflow:jump` | Select a numeric or named workspace |
| `hl.plugin.hyprflow.accept()` | `hyprflow:accept` | Activate the selection |
| `hl.plugin.hyprflow.cancel()` | `hyprflow:cancel` | Return to the original workspace |

For example:

```sh
hyprctl dispatch hyprflow:toggle
hyprctl dispatch hyprflow:jump 4
hyprctl eval 'hl.plugin.hyprflow.left()'
hyprctl repl 'return hl.plugin.hyprflow.status()'
```

## Custom bindings

```lua
hl.bind("SUPER + F", function() hl.plugin.hyprflow.toggle() end)
hl.bind("SUPER + ALT + Right", function()
    hl.plugin.hyprflow.right()
end, { repeating = true })
```

Keep the default modal submap when adding bindings. Its `catchall` consumes unrelated keys, including keys that could otherwise reach an input method. The previous submap and client focus are restored on exit.

# Troubleshooting

## The plugin rejects an API hash

The running compositor and build headers must match exactly. Check `hyprctl version` and `pkg-config --modversion hyprland`, install matching headers, and rebuild. The version number alone may not distinguish two different builds; Hyprflow checks the full API hash.

## A build dependency is missing

```sh
pkg-config --modversion hyprland lua5.4 egl glesv2 pangocairo
```

Install the missing development packages from your distribution. The plugin requires a C++23 compiler. Website builds use Node.js separately; they do not compile the plugin.

## Bindings do nothing

Confirm the plugin loaded with `hyprctl plugin list`, then source the default configuration. Test `hyprctl dispatch hyprflow:toggle` to distinguish plugin loading from a keybinding conflict. The nested demo uses **F10**; the normal configuration uses **Super + Tab**.

## A workspace is missing

Navigation covers the focused monitor. Other monitors and special workspaces are intentionally excluded. Increase `workspace_count` to add numeric cards, or use an existing named workspace on the focused monitor.

## The flow shows black bars

Wide desktops fit inside square covers without cropping or distortion. Black matte padding is intentional. See the [animation specification](design-spec.md#workspace-imagery-and-lighting).

## Report a problem

Include the compositor version, renderer, build output, plugin configuration, steps to reproduce, and whether the issue also occurs in the [nested session](getting-started.md#try-an-isolated-session). File an [issue on GitHub](https://github.com/sandwichfarm/hyprflow/issues).

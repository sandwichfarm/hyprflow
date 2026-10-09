# Troubleshooting

## Hyprpm cannot install or load Hyprflow

Run `hyprpm update` before the first `hyprpm add`. Hyprpm needs its matching
Hyprland headers and build tools; `hyprpm -v update` shows detailed build errors.
Check `hyprpm list` for a failed build or disabled plugin, then run
`hyprpm enable hyprflow` and `hyprpm reload`. Confirm loading with
`hyprctl plugin list` and inspect `hyprctl configerrors`.

Hyprflow targets Hyprland **0.56.2 / OpenGL**. The manifest skips older
compositor revisions. Newer versions may need plugin changes even when hyprpm
can prepare their headers. Do not bypass the plugin's API hash check.

## The plugin rejects an API hash

The running compositor and build headers must match exactly. For a hyprpm install, restart into the installed Hyprland version, then run `hyprpm update` and `hyprpm reload`. Hyprpm manages its own header cache. For a manual build, check `hyprctl version` and `pkg-config --modversion hyprland`, install matching headers, and rebuild. The version number alone may not distinguish two different builds; Hyprflow checks the full API hash.

## A build dependency is missing

```sh
pkg-config --modversion hyprland lua5.4 egl glesv2 pangocairo
```

Install the missing development packages from your distribution. The plugin requires a C++23 compiler. Website builds use Node.js separately; they do not compile the plugin.

## Bindings do nothing

Confirm the plugin loaded with `hyprctl plugin list`, then add the [quick-start bindings](getting-started.md#set-up-controls) or source the full configuration and run `hyprctl reload`. Test `hyprctl dispatch hyprflow:toggle` to distinguish plugin loading from a keybinding conflict. The nested demo uses **F10**; the normal configuration uses **Super + Tab**. If it works after a manual `hyprpm reload` but not after login, add the startup callback from the installation guide.

## A workspace is missing

Navigation covers the focused monitor. Other monitors and special workspaces are intentionally excluded. Increase `workspace_count` to add numeric cards, or use an existing named workspace on the focused monitor.

## The flow shows black bars

Wide desktops fit inside square covers without cropping or distortion. Black matte padding is intentional. See the [animation specification](design-spec.md#workspace-imagery-and-lighting).

## Report a problem

Include the compositor version, renderer, build output, plugin configuration, steps to reproduce, and whether the issue also occurs in the [nested session](getting-started.md#try-an-isolated-session). File an [issue on GitHub](https://github.com/sandwichfarm/hyprflow/issues).

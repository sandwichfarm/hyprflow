---
name: hyprflow-config
description: Implement Hyprflow options, defaults, validation, Lua controls, and reload behavior with matching runtime tests and docs.
---

# Implement configuration behavior

Keep visible nested test windows confined to host workspace 5, launched silently with
no focus and never pinned. Use the owned-session helper instead of launching a compositor
directly or moving a new window after it has already appeared on another workspace.
Headless sessions avoid GUI disruption when the affected behavior permits them.
Use headless outputs for automated multi-output cases: the initial GUI launch's
process-scoped exec rule expires after one minute and does not qualify later GUI windows.

Work from the repository root. Read the affected option's registration and consumption
before editing; names in a config file alone do not establish behavior.

## Locate the contract

- `src/Config.hpp` and `src/Config.cpp`: appearance defaults, native value registration,
  parsing, last-valid values, and deduplicated rejection diagnostics.
- `src/main.cpp`: `workspace_count`, `select_on_release`, action registration, and lifecycle listeners.
- `config/hyprflow.lua`: complete shipped defaults and modal bindings.
- `docs/configuration.md`: public ranges, syntax, precedence, and update timing; `README.md` summarizes these.

For a new option, decide its type, default, valid range, invalid-value policy, and when
changes become effective. Follow the existing responsible layer rather than introducing a second config store.

## Preserve the non-obvious behavior

Appearance options are read at render time and after config reloads. In Hyprland 0.56.2,
the Lua plugin conversion can discard registered bounds and string validators.
Keep application-time validation: a successful `hl.config()` or raw `getoption` value
is not proof that an appearance setting was applied.

For appearance validation, preserve the previous valid value on invalid input and avoid
repeated notifications for the same invalid value. A valid value must recover normally.
Update the matching fixed-size arrays and rejection indexes when extending those groups.
Do not silently extend that policy to options with a different contract:
`workspace_count` is clamped when creating a flow; `select_on_release` is sampled on creation.

Use the native types deliberately. `workspace_overlay` and `show_labels` are numeric
`0`/`1` switches; `select_on_release` is a Lua boolean and defaults to `false`.
Keep C++ defaults, the shipped Lua config, and documented defaults aligned.

For colors, reuse the existing parsers and precedence. An empty role override means
inheritance; transparent means an explicit transparent border. Do not introduce CSS
color syntax or legacy aliases merely to make an example parse.

## Lua controls and reloads

Keep the plugin-loaded guard in `config/hyprflow.lua`: startup config can run before
plugin functions exist. Preserve the modal submap's `catchall` and prior-submap restoration.
Return/Escape use `ignore_mods` so they work during held-modifier navigation.
Release selection tracks the opening chord inside the plugin; its Lua actions remain
on key press. Changes to acceptance must preserve explicit cancel/toggle disarming.

For a behavior change, update its existing proof or add a focused failing assertion
before relying on a passing result. Cover defaults, a changed valid value, relevant
boundaries/invalid inputs, recovery, and runtime/file reload as applicable.
Use [configuration proof](../hyprflow-config-proof/SKILL.md) for compositor verification.

Finish by updating the shipped example and public docs for implemented behavior only.
State update timing and any preserved compatibility limit rather than implying every
option takes effect immediately or that every renderer is supported.

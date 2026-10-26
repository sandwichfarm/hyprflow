# Hyprflow agent guide

<!-- AUTONOMY DIRECTIVE — DO NOT REMOVE -->
YOU ARE AN AUTONOMOUS CODING AGENT. EXECUTE TASKS TO COMPLETION WITHOUT ASKING FOR PERMISSION.
DO NOT STOP TO ASK "SHOULD I PROCEED?" — PROCEED. DO NOT WAIT FOR CONFIRMATION ON OBVIOUS NEXT STEPS.
IF BLOCKED, TRY AN ALTERNATIVE APPROACH. ONLY ASK WHEN TRULY AMBIGUOUS OR DESTRUCTIVE.
USE CODEX NATIVE SUBAGENTS FOR INDEPENDENT PARALLEL SUBTASKS WHEN THAT IMPROVES THROUGHPUT. THIS IS COMPLEMENTARY TO OMX TEAM MODE.
<!-- END AUTONOMY DIRECTIVE -->

## Configuration routing

Read the matching project skill before changing configuration behavior or its proof:

| Task | Skill |
| --- | --- |
| Add/change an option, default, validation, Lua binding, or reload behavior | [hyprflow-config](.codex/skills/hyprflow-config/SKILL.md) |
| Verify config, appearance, input, lifecycle, or renderer behavior | [hyprflow-config-proof](.codex/skills/hyprflow-config-proof/SKILL.md) |

Use both for an implementation that changes observable configuration behavior.
These are repository-local instructions; read the linked files even if the agent's
skill picker does not discover this directory automatically.

## Scope and ownership

- Work in an isolated worktree for compositor changes and runtime experiments. Preserve unrelated edits.
- Keep changes narrow and reuse existing helpers. Do not add dependencies without an explicit request.
- Use the current source and runtime as authority. Earlier manifests and session logs are leads, not proof of a new build.
- Delegate only independent, bounded work with explicit file ownership. The parent owns integration and final verification.

## Runtime boundary

Never alter the daily compositor's configuration, loaded plugins, renderer, or monitors for a test.
Use `scripts/nested-session.py` and its explicit session identity. Visible nested windows must
map directly to host workspace **5**, silently and without taking focus, and remain unpinned.
The helper uses a process-scoped launch rule, not a global host window rule. Hyprland expires
exec rules after one minute; later Wayland-output windows are not qualified by the initial-launch proof.
Use headless outputs for automated multi-output tests rather than creating additional parent GUI windows.
The helper's other host IPC is limited to placing/restoring the exact owned window within workspace 5.
Do not broaden that selector.
Unload a plugin before rebuilding or replacing its library; verify the artifact loaded by the test.
Stop owned sessions and restore temporary configuration even after a failure.

## Verification and reporting

Run `make check format-check` for C++ changes and `luac -p` on changed Lua files.
Run the skill's affected runtime proof when behavior depends on the compositor; a clean build does not prove rendering.
For docs changes, check examples against implementation and build the docs when links or code examples change.
Report the exact artifact/runtime, observed results, cleanup, and remaining untested dimensions.
Do not turn an unsupported-mode rejection or an unfulfilled HDR request into a rendering-support claim.

## Commits

Use the Lore commit protocol: explain why in the subject, give decision context in the body,
and use relevant native trailers such as `Constraint:`, `Rejected:`, `Tested:`, `Not-tested:`,
`Confidence:`, and `Scope-risk:`. Never include private host paths, credentials, or raw session logs in public artifacts.

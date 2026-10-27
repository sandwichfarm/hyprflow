# Vulkan output guard proof

This test-only helper exercises Hyprflow's rejection/reset boundary in an owned
qualified Vulkan compositor. It temporarily changes the focused monitor's transform
inside one callback and restores it before returning. It does not change the output
configuration or qualify native rotated rendering.

Build the helper against the same qualified SDK as the loaded plugin:

```sh
g++ -std=c++23 -O2 -g -fPIC -fno-gnu-unique -shared -Wl,--as-needed \
    probe.cpp $(pkg-config --cflags --libs hyprland lua5.4) -o guard-probe.so
```

Run the verifier with a standard owned session containing workspaces 4 and 5, a
closed Hyprflow switcher, and the candidate artifact already loaded. The verifier
checks artifact identity, loads only the test helper, and removes it afterward.
Use the qualification SDK's pkg-config environment. Never load this helper in the
daily compositor.

`receipt.json` records the original before/after proof. The old candidate opened
under an unsupported transform and remained open after the pre-render event; the
fixed candidate rejects opening, permits accept/cancel, and closes before drawing
when the transform changes. Native rotated output's independent failure remains
recorded separately.

```sh
python3 verify-vulkan-output-guards.py "$session_dir" /tmp/hyprflow-guard-proof \
    --repo "$repo_root" --artifact "$artifact" --sha256 "$artifact_sha" \
    --probe "$PWD/guard-probe.so"
```

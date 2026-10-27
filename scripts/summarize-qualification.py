#!/usr/bin/env python3
"""Validate passing runtime receipts and export a compact report without private session data."""

import argparse
import json
from pathlib import Path


if not __debug__:
    raise SystemExit("Run acceptance proofs without -O/PYTHONOPTIMIZE; assertions are required.")

def summarize(path):
    data = json.loads(path.read_text())
    assert data.get("passed") is True, f"Unsuccessful receipt: {path}"
    assert not any(data.get(key) for key in ("error", "cleanup_error", "configerrors")), "Receipt contains an error"
    assert data.get("checks") or data.get("attempts"), "Receipt contains no checks"
    if "attempts" in data:
        assert data.get("runtime_survived") is True and len(data["attempts"]) == 3, "Incomplete rejection proof"
    if "final_status" in data:
        assert data["final_status"] == {"open": False}, "Receipt did not finish closed"
        assert not data.get("configerrors"), "Receipt has config errors"
        assert not data.get("cleanup_forced_unload"), "Receipt needed a forced flow cleanup"
    isolation = data.get("input_isolation")
    if isolation and isolation.get("present"):
        assert isolation.get("restored") is True, "Input isolation was not restored"
    if data.get("frames"):
        import hashlib
        for frame in data["frames"]:
            image = path.parent / frame["file"]
            assert image.resolve().parent == path.parent.resolve(), "Frame escaped receipt directory"
            assert hashlib.sha256(image.read_bytes()).hexdigest() == frame["sha256"], "Frame hash differs"
    names = []
    outputs = []
    for index, check in enumerate(data.get("checks", [])):
        if isinstance(check, str):
            names.append(check)
            continue
        assert check.get("passed", True) is True
        names.append(check.get("name", f"check_{index + 1}"))
        if "output" in check:
            requested, effective = check["output"]["requested"], check["output"]["effective"]
            outputs.append({"check": check["name"], "requested": requested,
                            "effective": {key: effective[key] for key in
                                          ("width", "height", "scale", "transform", "currentFormat", "colorManagementPreset")}})
    profile = data.get("profile")
    if profile:
        assert profile in ("full", "vulkan-sdr"), "Unknown matrix profile"
        geometry = [(1, 0), (1.25, 0), (1.5, 0), (2, 0)]
        if profile == "full":
            geometry += [(1, 1), (1, 2), (1, 3), (1, 4), (1.25, 1)]
        required = {f"scale-{scale}-transform-{transform}" for scale, transform in geometry}
        required |= {f"unload_reload_{i:02d}" for i in range(1, 11)}
        required.add("cross-monitor-exclusion-and-active-output-removal")
        required.add("scale-and-rotation-change-while-open" if profile == "full" else "scale-change-while-open")
        color_cases = [("wide", 8, False), ("srgb", 10, False), ("hdr", 10, False), ("hdr", 10, True)]
        if profile == "vulkan-sdr":
            color_cases = [("srgb", 8, False)]
        required |= {f"color-{cm}-{depth}-forced-{forced}" for cm, depth, forced in color_cases}
        assert required <= set(names), "Incomplete matrix profile"
        assert data.get("frames"), "Matrix has no screenshot receipts"
    result = {"passed": True, "checks": names, "check_count": len(names)}
    for key in ("artifact_sha256", "artifact_mapping_verified", "phase", "profile", "limits", "duration_seconds"):
        if key in data:
            result[key] = data[key]
    if outputs:
        result["outputs"] = outputs
    if "attempts" in data:
        result["rejections"] = data["attempts"]
        result["runtime_survived"] = data["runtime_survived"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proof", nargs="+", help="Public label=private receipt path")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scopes = {}
    for entry in args.proof:
        label, path = entry.split("=", 1)
        assert label and label not in scopes, "Duplicate or empty public label"
        scopes[label] = summarize(Path(path))
    text = json.dumps({"scopes": scopes}, indent=2) + "\n"
    assert not any(marker in text for marker in ("/home/", "/tmp/")), "Private session data in public export"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text)
    print("Qualification receipts verified")


if __name__ == "__main__":
    main()

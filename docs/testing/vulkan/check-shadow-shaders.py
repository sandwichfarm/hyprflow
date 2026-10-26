#!/usr/bin/env python3
"""Compile native Vulkan shadow variants against the source tree's shared helpers."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess

FEATURES = ('RGBA', 'DISCARD', 'TINT', 'ROUNDING', 'CM', 'TONEMAP', 'SDR_MOD', 'BLUR', 'ICC', 'MIRROR')


def flatten(path, root, features):
    if path.name == 'defines.h':
        return '\n'.join(f'#define USE_{name} {features.get(name, 0)}' for name in FEATURES) + '\n'
    return re.sub(r'^\s*#include "([^"]+)"\s*$',
                  lambda match: flatten(root / match.group(1), root, features), path.read_text(), flags=re.M)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('src/render/shaders/glsl'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.source.resolve(strict=True)
    args.output.mkdir(parents=True, exist_ok=True)
    cases = []
    for rounding, cm, tonemap, sdr in itertools.product((0, 1), repeat=4):
        if not cm and (tonemap or sdr):
            continue
        features = dict(ROUNDING=rounding, CM=cm, TONEMAP=tonemap, SDR_MOD=sdr, RGBA=1)
        name = 'shadow-' + ''.join(map(str, (rounding, cm, tonemap, sdr)))
        path = args.output / (name + '.frag')
        path.write_text(flatten(root / 'vk_shadow.frag', root, features))
        result = subprocess.run(['glslangValidator', '-V', '-S', 'frag', str(path), '-o', str(path.with_suffix('.spv'))],
                                text=True, capture_output=True)
        cases.append(dict(name=name, features=features, passed=result.returncode == 0,
                          diagnostics=result.stdout + result.stderr))
    receipt = dict(passed=all(case['passed'] for case in cases), cases=cases,
                   shader_sha256=hashlib.sha256((root / 'vk_shadow.frag').read_bytes()).hexdigest())
    (args.output / 'results.json').write_text(json.dumps(receipt, indent=2) + '\n')
    assert receipt['passed'], 'At least one shadow variant failed; inspect results.json'
    print(f'PASS {len(cases)} native Vulkan shadow variants')


if __name__ == '__main__':
    main()

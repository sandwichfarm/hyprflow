#!/usr/bin/env python3
"""Check a plugin-free owned Vulkan session with core and sync validation active."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import time
from PIL import Image


def validation_errors(text):
    return [line for line in text.splitlines() if 'Validation Error:' in line or 'SYNC-HAZARD-' in line]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--positive-control', type=Path, required=True)
    args = parser.parse_args()
    helper = runpy.run_path(str(args.project / 'scripts/nested-session.py'))
    state = json.loads(args.session.read_text())
    helper['session'](state['directory'])
    args.output.mkdir(parents=True, exist_ok=True)
    control = lambda *parts: helper['control'](state, *parts).stdout
    log = Path(state['directory']) / 'compositor.log'
    assert validation_errors(args.positive_control.read_text(errors='replace')), 'Missing positive validation-error control'
    assert not validation_errors(log.read_text(errors='replace'))
    assert control('plugin', 'list').strip() == 'no plugins loaded'
    assert json.loads(control('-j', 'getoption', 'render:cm_sdr_eotf'))['str'] == 'default'
    assert 'libVkLayer_khronos_validation.so' in Path(f'/proc/{state["pid"]}/maps').read_text()
    with (args.output / 'fixture.log').open('w') as fixture_log:
        subprocess.Popen(
            ['kitty', '--config', 'NONE', '--class', 'hyprflow-vulkan-native-validation',
             '--title', 'Native Vulkan validation fixture', '-o', 'confirm_os_window_close=0',
             '-o', 'background=#21436a', '-o', 'font_size=22', '-o', 'cursor_blink_interval=0',
             'sh', '-c', 'printf "AMD Vulkan native validation\nDefault SDR color contract\n"; sleep 600'],
            env=helper['environment'](state), stdout=fixture_log, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(60):
        clients = json.loads(control('-j', 'clients'))
        if any(client['class'] == 'hyprflow-vulkan-native-validation' for client in clients):
            break
        time.sleep(.1)
    else:
        raise RuntimeError('Native fixture did not map')
    proof = dict(passed=False, native_only=True, renderer='Vulkan', gpu='AMD Radeon RX Vega / RADV',
                 configuration_eotf='default', checks=[], validation_errors=[],
                 runtime_binary_sha256=hashlib.sha256(Path(state['compositor']).read_bytes()).hexdigest())

    def capture(name):
        image = args.output / (name + '.png')
        subprocess.run(['grim', '-o', 'HEADLESS-2', str(image)], env=helper['environment'](state),
                       check=True, timeout=10, capture_output=True)
        pixels = Image.open(image).convert('RGB')
        pixel = pixels.getpixel((640, 500))
        colors = pixels.getcolors(pixels.width * pixels.height)
        assert all(abs(actual - expected) <= 1 for actual, expected in zip(pixel, (33, 67, 106))), (name, pixel)
        assert colors and len(colors) > 100
        errors = validation_errors(log.read_text(errors='replace'))
        assert not errors, errors
        proof['checks'].append(dict(name=name, pixel=list(pixel), sha256=hashlib.sha256(image.read_bytes()).hexdigest()))
        print(name, 'passed', flush=True)

    for index in range(1, 4):
        control('reload')
        assert not control('configerrors').strip()
        time.sleep(.15)
        capture('reload-' + str(index))
    for index in range(10):
        control('dispatch', 'hl.dsp.window.fullscreen({action="toggle"})')
        control('dispatch', 'hl.dsp.window.fullscreen({action="toggle"})')
        capture('native-roundtrip-' + str(index))
    time.sleep(.3)
    raw = log.read_text(errors='replace')
    assert not validation_errors(raw), validation_errors(raw)
    assert 'Insert instance layer "VK_LAYER_KHRONOS_validation"' in raw
    assert control('plugin', 'list').strip() == 'no plugins loaded'
    assert control('repl', 'return 42').strip() == '42'
    assert not control('configerrors').strip()
    helper['session'](state['directory'])
    proof.update(passed=True, validation_error_positive_control=True, validation_layer_loaded=True,
                 plugins='no plugins loaded', repl=42)
    (args.output / 'summary-public.json').write_text(json.dumps(proof, indent=2) + '\n')
    print('NATIVE VVL BASELINE PASS', len(proof['checks']), proof['runtime_binary_sha256'], flush=True)


if __name__ == '__main__':
    main()

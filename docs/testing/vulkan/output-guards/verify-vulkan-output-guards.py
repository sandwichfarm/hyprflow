#!/usr/bin/env python3
"""Verify Vulkan output rejection/reset with an atomic helper in an owned session."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument('output', type=Path)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--probe', type=Path, required=True)
    args = parser.parse_args()
    helper = runpy.run_path(str(args.repo.resolve() / 'scripts/nested-session.py'))
    state = helper['session'](args.directory)
    artifact, probe = args.artifact.resolve(strict=True), args.probe.resolve(strict=True)
    assert artifact != probe, 'The test helper must be separate from the main plugin'
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == args.sha256, 'Artifact hash differs'
    maps = Path(f'/proc/{state["pid"]}/maps').read_text()
    entries = [line for line in maps.splitlines() if line.split(maxsplit=5)[-1] == str(artifact)]
    assert entries and all(int(line.split()[4]) == artifact.stat().st_ino for line in entries), 'Mapped candidate inode differs'
    assert 'libVkLayer_khronos_validation.so' in maps, 'Use a session with validation enabled'
    args.output.mkdir(parents=True, exist_ok=True)
    assert not any(args.output.iterdir()), 'Use an empty evidence directory'
    receipt = dict(passed=False, artifact_sha256=args.sha256, checks=[],
                   method='Atomic temporary transform; no physical output rotation is applied')
    loaded = False

    def control(*values):
        helper['session'](args.directory)
        return helper['control'](state, *values).stdout.strip()

    def status():
        return json.loads(control('repl', 'return hl.plugin.hyprflow.status()'))

    def action(name, argument=''):
        control('eval', f'hl.plugin.hyprflow.{name}({argument})')

    def wait(selected):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            actual = status()
            if selected is None and not actual['open']:
                return
            if (selected is not None and actual.get('selected') == selected and not actual.get('closing')
                    and actual.get('openness', 0) > .999 and abs(actual['position'] - (selected - 1)) < .001):
                return
            time.sleep(.025)
        raise AssertionError(actual)

    assert not status()['open'], 'Start with the switcher closed'
    original_workspace = json.loads(control('-j', 'activeworkspace'))['id']
    initial_submap = control('submap')
    assert 'hyprflow_guard_probe' not in control('plugin', 'list'), 'Probe is already loaded'
    try:
        control('plugin', 'load', str(probe))
        loaded = True
        assert control('repl', 'return type(hl.plugin.hyprflow_guard_probe.unsupported_open)') == 'function'
        control('dispatch', 'hl.dsp.focus({workspace=4})')
        result = control('repl', 'local ok,err=hl.plugin.hyprflow_guard_probe.unsupported_open(); return tostring(ok).."\\n"..err')
        assert result.startswith('false\n') and 'unrotated' in result
        assert not status()['open'] and control('submap') == initial_submap
        receipt['checks'].append('unsupported opening rejected explicitly without changing submap')
        for exit_action, destination in (('cancel', 4), ('accept', 5)):
            action('jump', '5')
            wait(5)
            result = control('repl', f'local ok=hl.plugin.hyprflow_guard_probe.unsupported_action("{exit_action}"); return tostring(ok)')
            assert result == 'true'
            wait(None)
            assert json.loads(control('-j', 'activeworkspace'))['id'] == destination
            receipt['checks'].append(f'{exit_action} remains allowed')
            control('dispatch', 'hl.dsp.focus({workspace=4})')
        action('jump', '5')
        wait(5)
        control('eval', 'hl.plugin.hyprflow_guard_probe.unsupported_pre_render()')
        assert not status()['open'] and control('submap') == initial_submap
        assert json.loads(control('-j', 'activeworkspace'))['id'] == 4
        receipt['checks'].append('mid-flow transform closes before capture/draw and restores origin/submap')
        receipt['passed'] = True
    except Exception as error:
        receipt['error_type'] = type(error).__name__
        raise
    finally:
        if helper['running'](state['pid'], state['start_time']):
            if status()['open']:
                action('cancel')
                wait(None)
            if loaded:
                control('plugin', 'unload', str(probe))
            control('dispatch', f'hl.dsp.focus({{workspace={original_workspace}}})')
        (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('PASS Vulkan output guards')


if __name__ == '__main__':
    main()

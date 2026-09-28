"""Trusted JS transform boundary; synthetic source is never imported by Python."""
from pathlib import Path
import shutil

import pytest

from jev_integration_evaluator.integrations.js_backend import transform_js_source
from jev_integration_evaluator.io import InputError


TOOLING = Path(__file__).resolve().parents[1]
PINNED = TOOLING / 'node_modules' / 'typescript' / 'lib' / 'typescript.js'
BINDINGS = {'registry': 'hostRegistry', 'gate': 'hostGate', 'validate': 'hostValidate',
            'blocked': 'hostBlocked', 'evidence': 'hostEvidence',
            'baseline_action': 'hostBaseline'}
HELPERS = ''.join(f'function {name}(request) {{ return request; }}\n'
                  for name in BINDINGS.values())
pytestmark = pytest.mark.skipif(shutil.which('node') is None or not PINNED.is_file(),
                                reason='Trusted Node/TypeScript 5.8.3 tooling absent')


def test_transform_uses_only_pinned_outside_tooling(tmp_path):
    host = tmp_path / 'target'
    host.mkdir()
    (host / 'host.mjs').write_text(
        'export async function seam(request) { return await original(request); }\n'
        'async function original(request) { return request.task_id; }\n' + HELPERS,
        encoding='utf-8')
    (host / 'node_modules' / 'typescript').mkdir(parents=True)
    (host / 'node_modules' / 'typescript' / 'index.js').write_text(
        'throw Error("target plugin loaded")', encoding='utf-8')
    result = transform_js_source(host, 'host.mjs', symbol='seam', original='original',
                                 adapter_alias='jevAdapter', adapter_path='./jev_adapter.cjs',
                                 bindings=BINDINGS,
                                 tooling_dir=TOOLING)
    assert result['format'] == 'esm'
    assert result['compiler_version'] == '5.8.3'
    assert 'return await jevAdapter.invoke(original, request, {' in result['transformed_source']
    with pytest.raises(InputError, match='outside the target'):
        transform_js_source(host, 'host.mjs', symbol='seam', original='original',
                            adapter_alias='jevAdapter', adapter_path='./jev_adapter.cjs',
                            bindings=BINDINGS,
                            tooling_dir=host)


def test_unsupported_source_is_rejected_without_source_in_error(tmp_path):
    host = tmp_path / 'target'
    host.mkdir()
    secret_marker = 'PRIVATE_SYNTHETIC_SOURCE_MARKER'
    (host / 'host.mjs').write_text(
        'export async function seam(request) { return await original(other); }\n'
        'async function original(request) { return "' + secret_marker + '"; }\n' + HELPERS,
        encoding='utf-8')
    with pytest.raises(InputError) as exc:
        transform_js_source(host, 'host.mjs', symbol='seam', original='original',
                            adapter_alias='jevAdapter', adapter_path='./jev_adapter.cjs',
                            bindings=BINDINGS,
                            tooling_dir=TOOLING)
    assert secret_marker not in str(exc.value)

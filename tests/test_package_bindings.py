"""Static package resolution never imports or executes host modules."""
import os
from pathlib import Path

import pytest

from jev_integration_evaluator.integrations.errors import MissingBinding, UnsupportedShape
from jev_integration_evaluator.integrations.package_bindings import StaticBindings, module_layout


def write(root: Path, rel: str, contents: str):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding='utf-8')


def test_flat_and_src_relative_reexport_without_running_hooks(tmp_path):
    write(tmp_path, 'flat.py', 'def callback(request):\n    return request\n')
    flat = StaticBindings(tmp_path, 'flat.py')
    assert flat.resolve('callback')[:2] == ('flat.py', 'callback')
    assert set(flat.dependencies) == {'flat.py'}
    write(tmp_path, 'src/pkg/__init__.py', '"""Static package."""\n')
    write(tmp_path, 'src/pkg/callbacks.py', 'def callback(request):\n    return request\n')
    write(tmp_path, 'src/pkg/host.py', 'from .callbacks import callback as selected\n')
    resolver = StaticBindings(tmp_path, 'src/pkg/host.py')
    assert resolver.resolve('selected')[:2] == ('src/pkg/callbacks.py', 'callback')
    assert set(resolver.dependencies) == {'src/pkg/__init__.py', 'src/pkg/host.py', 'src/pkg/callbacks.py'}


def test_declared_namespace_requires_explicit_choice(tmp_path):
    write(tmp_path, 'src/ns/host.py', 'def callback(request):\n    return request\n')
    with pytest.raises(UnsupportedShape, match='initializer'):
        StaticBindings(tmp_path, 'src/ns/host.py')
    assert StaticBindings(tmp_path, 'src/ns/host.py', namespace=True).module == 'ns.host'


def test_dynamic_package_initializer_fails_without_execution(tmp_path):
    write(tmp_path, 'pkg/__init__.py', 'raise AssertionError("must not execute")\n')
    write(tmp_path, 'pkg/host.py', 'def callback(request):\n    return request\n')
    with pytest.raises(UnsupportedShape, match='Dynamic or external package initializer'):
        StaticBindings(tmp_path, 'pkg/host.py')


def test_external_initializer_import_is_rejected_before_execution(tmp_path):
    write(tmp_path, 'pkg/__init__.py', 'from external_hook import callback\n')
    write(tmp_path, 'pkg/host.py', 'def callback(request):\n    return request\n')
    with pytest.raises(UnsupportedShape, match='external package initializer'):
        StaticBindings(tmp_path, 'pkg/host.py')


@pytest.mark.parametrize(('source', 'error'), [
    ('from .other import callback\ncallback = None\n', MissingBinding),
    ('from .other import callback\nif FLAG:\n    callback = None\n', MissingBinding),
    ('def callback(request):\n    return request\ncallback = None\n', MissingBinding),
    ('from .host import callback\n', UnsupportedShape),
    ('from external import callback\n', UnsupportedShape),
    ('callback = lambda request: request\n', UnsupportedShape),
])
def test_ambiguous_cyclic_dynamic_external_rejected(tmp_path, source, error):
    write(tmp_path, 'pkg/__init__.py', '')
    write(tmp_path, 'pkg/other.py', 'def callback(request):\n    return request\n')
    write(tmp_path, 'pkg/host.py', source)
    with pytest.raises(error): StaticBindings(tmp_path, 'pkg/host.py').resolve('callback')


def test_source_dependency_hash_changes(tmp_path):
    write(tmp_path, 'pkg/__init__.py', '')
    write(tmp_path, 'pkg/other.py', 'def callback(request):\n    return request\n')
    write(tmp_path, 'pkg/host.py', 'from .other import callback\n')
    before = StaticBindings(tmp_path, 'pkg/host.py')
    before.resolve('callback')
    write(tmp_path, 'pkg/other.py', 'def callback(request):\n    return None\n')
    after = StaticBindings(tmp_path, 'pkg/host.py')
    after.resolve('callback')
    assert before.dependencies['pkg/other.py'] != after.dependencies['pkg/other.py']


def test_contributing_module_declared_non_utf8_is_rejected(tmp_path):
    write(tmp_path, 'pkg/__init__.py', '')
    write(tmp_path, 'pkg/host.py', 'from .other import callback\n')
    write(tmp_path, 'pkg/other.py', '# coding: latin-1\ndef callback(request):\n    return request\n')
    with pytest.raises(UnsupportedShape, match='declare UTF-8'):
        StaticBindings(tmp_path, 'pkg/host.py').resolve('callback')


def test_static_reexport_chain_records_every_module(tmp_path):
    write(tmp_path, 'pkg/__init__.py', 'from .exports import callback\n')
    write(tmp_path, 'pkg/host.py', 'from . import callback\n')
    write(tmp_path, 'pkg/exports.py', 'from .functions import callback\n')
    write(tmp_path, 'pkg/functions.py', 'def callback(request):\n    return request\n')
    resolver = StaticBindings(tmp_path, 'pkg/host.py')
    assert resolver.resolve('callback')[:2] == ('pkg/functions.py', 'callback')
    assert set(resolver.dependencies) == {'pkg/__init__.py', 'pkg/host.py', 'pkg/exports.py', 'pkg/functions.py'}


def test_dynamic_namespace_rebinding_rejected(tmp_path):
    write(tmp_path, 'pkg/__init__.py', '')
    write(tmp_path, 'pkg/host.py', 'from .other import callback\nglobals()["callback"] = None\n')
    write(tmp_path, 'pkg/other.py', 'def callback(request):\n    return request\n')
    with pytest.raises(UnsupportedShape, match='Dynamic module binding'):
        StaticBindings(tmp_path, 'pkg/host.py').resolve('callback')


@pytest.mark.parametrize('raised,reason', [
    (PermissionError(13, 'Permission denied', 'private-root/pkg/host.py'),
     'windows_source_read_access_denied'),
    (FileNotFoundError(2, 'No such file or directory', 'private-root/pkg/host.py'),
     'windows_source_read_unavailable')])
def test_selected_source_read_failure_is_platform_exact(tmp_path, monkeypatch, raised, reason):
    """Native Windows gets a fixed path-free reason; POSIX keeps the same error."""
    from jev_integration_evaluator.io import InputError, read_source

    write(tmp_path, 'pkg/__init__.py', '')
    write(tmp_path, 'pkg/host.py', 'def callback(request):\n    return request\n')
    assert StaticBindings(tmp_path, 'pkg/host.py').resolve('callback')[0] == 'pkg/host.py'
    assert read_source(tmp_path / 'pkg/host.py', Path.read_bytes).startswith(b'def callback')
    original = Path.read_bytes

    def failing(path):
        if path.name == 'host.py':
            raise raised
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', failing)
    for operation in (lambda: StaticBindings(tmp_path, 'pkg/host.py'),
                      lambda: read_source(tmp_path / 'pkg/host.py', Path.read_bytes)):
        with pytest.raises((OSError, InputError)) as caught:
            operation()
        if os.name == 'nt':
            assert type(caught.value) is InputError and caught.value.args == (reason,)
            assert caught.value.__cause__ is None and caught.value.__suppress_context__
            assert 'private-root' not in str(caught.value) and 'host' not in str(caught.value)
        else:
            assert caught.value is raised

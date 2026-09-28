import importlib.util
import json
import shutil
import sys
import zipfile
from pathlib import Path
import pytest
from jev_integration_evaluator.io import InputError, file_hash


def test_release_builder_uses_portable_manifest_order(root, tmp_path, monkeypatch):
    package = tmp_path / 'package'
    nested = package / 'validation' / 'generated-adapter'
    nested.mkdir(parents=True)
    (nested / 'WIRING.md').write_text('nested\n')
    (package / 'validation' / 'generated-adapter-test.txt').write_text('sibling\n')
    spec = importlib.util.spec_from_file_location('build_release_test', root / 'scripts/build_release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = package
    archive = tmp_path / 'release.zip'
    monkeypatch.setattr(sys, 'argv', ['build_release.py', '--out', str(archive)])
    module.main()
    manifest = (package / 'SHA256SUMS').read_text()
    paths = [line.split('  ', 1)[1] for line in manifest.splitlines()]
    assert paths == sorted(paths)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.read('package/SHA256SUMS').decode() == manifest


@pytest.fixture
def release_validator(root, tmp_path):
    destination = tmp_path / 'package'
    shutil.copytree(root, destination, ignore=shutil.ignore_patterns('.git', 'validation', 'node_modules', '__pycache__',
                        '.pytest_cache', '.venv', 'build', 'dist', '*.egg-info'))
    # Exclude large historical evidence, but include the current release's
    # required validation metadata in this otherwise complete package fixture.
    current_validation = json.loads((root / 'skill-package.json').read_text())['validation']
    (destination / current_validation).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / current_validation, destination / current_validation)
    for path in ('validation/path-corpus-support-v1.json',
                 'validation/PATH-CORPUS-CURRENT-SUPPORT.md',
                 'validation/JAVASCRIPT-TYPESCRIPT-SUPPORT.md'):
        (destination / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / path, destination / path)
    spec = importlib.util.spec_from_file_location('validate_test_copy', root / 'scripts/validate_package.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.ROOT = destination
    lines = [file_hash(p) + '  ' + p.relative_to(destination).as_posix() for p in sorted(destination.rglob('*'))
             if p.is_file() and p.name != 'SHA256SUMS' and p.suffix not in ('.zip', '.whl', '.pyc', '.pyo')]
    (destination / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')
    return module, destination


def test_exact_release_manifest_passes(release_validator):
    module, destination = release_validator
    assert module.validate(check_manifest=True)['manifest_files_verified'] > 100


@pytest.mark.parametrize('mutation', ['added', 'duplicate', 'traversal'])
def test_release_rejects_incomplete_or_unsafe_manifest(release_validator, mutation):
    module, destination = release_validator
    path = destination / 'SHA256SUMS'
    if mutation == 'added':
        (destination / 'unexpected.py').write_text('# unlisted code\n')
    elif mutation == 'duplicate':
        path.write_text(path.read_text() + path.read_text().splitlines()[0] + '\n')
    else:
        outside = destination.parent / 'outside.txt'; outside.write_text('not part of package')
        path.write_text(file_hash(outside) + '  ../outside.txt\n' + path.read_text())
    with pytest.raises(InputError): module.validate(check_manifest=True)

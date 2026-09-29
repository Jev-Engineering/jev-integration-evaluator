"""Read-only, source-bound catalog for the bounded JavaScript recipe C backend.

Rendering creates private planner inputs. It does not apply, install, or execute
the target. The existing js-* lifecycle retains all effect authority.
"""
from __future__ import annotations

import copy
import base64
import binascii
import os
import platform
from importlib.resources import files
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit

from . import __version__
from .contracts import validate_contract
from .io import InputError, digest, file_hash, read_json, safe_child, write_json
from .integrations import js_lifecycle

TEMPLATE_ID = 'javascript.recipe-c'
TEMPLATE_VERSION = '1.0.0'
RESOURCE = 'javascript-recipe-c.template.json'
SOURCE_PROFILE = 'flat-async-recipe-c-v1'
FORMATS = {'esm': '.mjs', 'commonjs': '.cjs', 'typescript': '.ts'}
SOURCE_SKIP = {'.git', 'node_modules', '.pytest_cache', '__pycache__'}
NAME = re.compile(r'^[a-z0-9][a-z0-9._-]{0,127}$')
VERSION = re.compile(r'^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$')
ENTRY = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*\.(?:mjs|cjs)$')


def _manifest() -> dict:
    manifest = read_json(Path(str(files('jev_integration_evaluator').joinpath('data', RESOURCE))))
    validate_contract(manifest, 'javascript-template-manifest-v1')
    if (manifest['template_id'] != TEMPLATE_ID or manifest['template_version'] != TEMPLATE_VERSION
            or manifest['evaluator_version'] != __version__):
        raise InputError('Packaged JavaScript template manifest differs from evaluator')
    return manifest


def inspect_js_template(template_id: str = TEMPLATE_ID, version: str = TEMPLATE_VERSION) -> dict:
    if template_id != TEMPLATE_ID or version != TEMPLATE_VERSION:
        raise InputError('Unsupported JavaScript template ID or version')
    manifest = _manifest()
    return copy.deepcopy(manifest) | {'manifest_sha256': digest(manifest)}


def _private_output(root: Path, output: str | Path) -> Path:
    out = Path(output).absolute()
    if any(part.is_symlink() for part in (out, *out.parents)):
        raise InputError('JavaScript template output traverses a symlink')
    out = out.resolve()
    if out == root or out.is_relative_to(root) or root.is_relative_to(out):
        raise InputError('JavaScript template output overlaps target')
    return out


def _host_file(root: Path, relative: str, limit: int = 2_000_000) -> Path:
    path = safe_child(root, relative)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise InputError('JavaScript package input missing, linked, or oversized')
    return path


def _source_tree(root: Path) -> dict[str, str]:
    """Bind every host source file, excluding only separately acquired tooling."""
    result = {}
    total = 0
    device = root.stat().st_dev
    def traversal_error(_):
        raise InputError('Node source tree could not be read')
    for base, dirs, names in os.walk(root, followlinks=False, onerror=traversal_error):
        for name in dirs + names:
            path = Path(base) / name
            info = path.lstat()
            if (stat.S_ISLNK(info.st_mode) or info.st_dev != device
                    or os.path.ismount(path)):
                raise InputError('Node source tree contains a link or mount')
        dirs[:] = sorted(name for name in dirs
                         if Path(base) != root or name not in SOURCE_SKIP)
        for name in sorted(names):
            path = Path(base) / name
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise InputError('Node source tree contains a nonregular file')
            total += info.st_size
            if len(result) >= 4096 or total > 64_000_000:
                raise InputError('Node source tree exceeds bounded profile')
            result[path.relative_to(root).as_posix()] = file_hash(path)
    return result


def _package(root: Path, request: dict, source_format: str) -> dict:
    package_path = _host_file(root, 'package.json')
    lock_path = _host_file(root, 'package-lock.json', 5_000_000)
    package = read_json(package_path, max_bytes=2_000_000)
    lock = read_json(lock_path, max_bytes=5_000_000)
    if type(package) is not dict or type(lock) is not dict:
        raise InputError('Invalid Node package or lock object')
    if (not NAME.fullmatch(str(package.get('name', '')))
            or not VERSION.fullmatch(str(package.get('version', '')))
            or package.get('scripts') != {'start': 'node ' + request['entrypoint']}
            or not ENTRY.fullmatch(request['entrypoint'])
            or (source_format == 'commonjs' and not request['entrypoint'].endswith('.cjs'))
            or (source_format != 'commonjs' and not request['entrypoint'].endswith('.mjs'))):
        raise InputError('Unsupported finite Node package start profile')
    forbidden = {'preinstall', 'install', 'postinstall', 'prepare', 'prepublish',
                 'prepublishOnly', 'postpublish', 'prestart', 'poststart', 'build'}
    if (forbidden & set(package.get('scripts', {}))
            or package.get('gypfile') is True or package.get('workspaces') is not None):
        raise InputError('Node package hooks, workspaces, and native builds unsupported')
    if (lock.get('lockfileVersion') != 3 or lock.get('name') != package['name']
            or lock.get('version') != package['version'] or type(lock.get('packages')) is not dict
            or type(lock['packages'].get('')) is not dict):
        raise InputError('Exact npm lockfileVersion 3 required')
    root_row = lock['packages']['']
    if (root_row.get('name') != package['name'] or root_row.get('version') != package['version']
            or root_row.get('dependencies', {}) != package.get('dependencies', {})
            or root_row.get('optionalDependencies', {}) != package.get('optionalDependencies', {})
            or root_row.get('devDependencies', {}) != package.get('devDependencies', {})):
        raise InputError('Node lock root differs from package manifest')
    if package.get('optionalDependencies') or package.get('devDependencies'):
        raise InputError('Optional and development target dependencies unsupported')
    dependencies = package.get('dependencies', {})
    if (type(dependencies) is not dict or len(dependencies) > 128
            or any(not NAME.fullmatch(str(name)) or not VERSION.fullmatch(str(version))
                   for name, version in dependencies.items())):
        raise InputError('Node dependencies must be bounded exact versions')
    if len(lock['packages']) > 129:
        raise InputError('Node lock dependency count exceeds declared profile')
    for name, row in lock['packages'].items():
        if type(name) is not str or type(row) is not dict:
            raise InputError('Invalid Node lock package row')
        if name == '':
            continue
        if (not name.startswith('node_modules/') or '..' in Path(name).parts
                or row.get('hasInstallScript') or row.get('link')
                or not re.fullmatch(r'sha512-[A-Za-z0-9+/]+={0,2}', str(row.get('integrity', '')))
                or type(row.get('resolved')) is not str):
            raise InputError('Unsupported Node dependency lock row')
        if (set(row) & {'dependencies', 'optionalDependencies', 'peerDependencies',
                        'bin', 'os', 'cpu', 'hasInstallScript', 'link', 'dev', 'optional'}
                or not VERSION.fullmatch(str(row.get('version', '')))):
            raise InputError('Unsupported Node dependency package behavior')
        try:
            integrity = base64.b64decode(row['integrity'][7:], validate=True)
            url = urlsplit(row['resolved'])
        except (ValueError, binascii.Error):
            raise InputError('Invalid Node dependency digest or source') from None
        if len(integrity) != 64:
            raise InputError('Invalid Node dependency digest length')
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.query or url.fragment or not url.path.endswith('.tgz')):
            raise InputError('Unsupported Node dependency source')
    if len(lock['packages']) - 1 != len(dependencies):
        raise InputError('Nested or unresolved Node dependency graph unsupported')
    for name, version in dependencies.items():
        if (not isinstance(lock['packages'].get('node_modules/' + name), dict)
                or lock['packages']['node_modules/' + name].get('version') != version):
            raise InputError('Node dependency absent from lock')
    entry = _host_file(root, request['entrypoint'], 500_000)
    if (file_hash(package_path) != request['package_json_sha256']
            or file_hash(lock_path) != request['package_lock_sha256']
            or file_hash(entry) != request['entrypoint_sha256']):
        raise InputError('Reviewed Node package or entrypoint changed')
    source_map = _source_tree(root)
    if not {'package.json', 'package-lock.json', request['entrypoint'],
            request['implementation_spec']['source']['file']} <= set(source_map):
        raise InputError('Required Node package source file absent')
    if digest(source_map) != request['reviewed_package_source_sha256']:
        raise InputError('Independently reviewed Node package source changed')
    return {'name': package['name'], 'version': package['version'],
            'entrypoint': request['entrypoint'], 'source_files': source_map,
            'source_sha256': digest(source_map), 'dependency_count': len(dependencies),
            'package_json_sha256': request['package_json_sha256'],
            'package_lock_sha256': request['package_lock_sha256'],
            'entrypoint_sha256': request['entrypoint_sha256']}


def validate_js_template_request(root: str | Path, request: dict, *, tooling_dir: str | Path) -> dict:
    validate_contract(request, 'javascript-template-request-v1')
    manifest = inspect_js_template(request['template_id'], request['template_version'])
    if request['backend'] != 'javascript' or request['profile'] != SOURCE_PROFILE:
        raise InputError('Unsupported JavaScript template backend or profile')
    spec = js_lifecycle._check_spec(request['implementation_spec'])
    if spec['recipe_id'] != 'javascript.C' or spec['runtime']['runtime']['mode'] != 'off':
        raise InputError('Unsupported JavaScript recipe or runtime mode')
    configuration = request['configuration']
    refs = request['secret_references']
    expected = ({} if configuration['credential_ref'] is None else
                {'credential': configuration['credential_ref']})
    if refs != expected or digest({'configuration': configuration, 'secret_references': refs}) != request['reviewed_configuration_sha256']:
        raise InputError('Reviewed JavaScript configuration or secret reference changed')
    source_root = Path(root).absolute()
    if any(part.is_symlink() for part in (source_root, *source_root.parents)):
        raise InputError('JavaScript source root traverses a symlink')
    root = js_lifecycle._root(source_root)
    if platform.machine().lower() not in {'x86_64', 'amd64'}:
        raise InputError('JavaScript template requires Linux x86-64')
    if not Path(tooling_dir).is_absolute():
        raise InputError('Trusted tooling path must be absolute')
    tooling = js_lifecycle._tooling(root, Path(tooling_dir))
    transformed, _ = js_lifecycle._generated(root, spec, Path(tooling_dir))
    if transformed['format'] != request['format']:
        raise InputError('Reviewed JavaScript module format changed')
    package = _package(root, request, transformed['format'])
    return {'schema_version': '1.0', 'status': 'validated', 'template_id': TEMPLATE_ID,
            'template_version': TEMPLATE_VERSION, 'manifest_sha256': manifest['manifest_sha256'],
            'evaluator_version': __version__, 'renderer_sha256': file_hash(Path(__file__)),
            'tooling': tooling, 'request_sha256': digest(request), 'spec_sha256': digest(spec),
            'candidate_id': spec['candidate_id'], 'format': transformed['format'],
            'source_sha256': spec['source']['sha256'], 'generated_sha256': transformed['generated_sha256'],
            'emitted_sha256': transformed['emitted_sha256'], 'package': package,
            'configuration_sha256': request['reviewed_configuration_sha256'],
            'secret_references_sha256': digest(refs), 'lifecycle': copy.deepcopy(manifest['lifecycle']),
            'target_modified': False, 'target_executed': False}


def materialize_js_template(root: str | Path, request: dict, output: str | Path,
                            *, tooling_dir: str | Path) -> dict:
    result = validate_js_template_request(root, request, tooling_dir=tooling_dir)
    target = js_lifecycle._root(Path(root))
    out = _private_output(target, output)
    trusted_tooling = Path(tooling_dir).resolve(strict=True)
    if out == trusted_tooling or out.is_relative_to(trusted_tooling) or trusted_tooling.is_relative_to(out):
        raise InputError('JavaScript template output overlaps trusted tooling')
    try:
        out.mkdir(mode=0o700, parents=True, exist_ok=False)
    except FileExistsError:
        raise InputError('JavaScript template output collision') from None
    os.chmod(out, 0o700)
    write_json(out / 'render-status.json', {'schema_version': '1.0', 'status': 'incomplete',
                                            'request_sha256': result['request_sha256']})
    resources = {'template-manifest.json': _manifest(), 'template-request.json': request,
                 'implementation-spec.json': request['implementation_spec'],
                 'package-profile.json': result['package']}
    for name, value in resources.items():
        write_json(out / name, value)
    hashes = {name: file_hash(out / name) for name in sorted(resources)}
    if validate_js_template_request(root, request, tooling_dir=tooling_dir) != result:
        raise InputError('JavaScript source or tooling changed during materialization')
    lock = result | {'status': 'materialized', 'owned_resources': hashes,
                     'planner': {'command': 'js-plan', 'spec': 'implementation-spec.json',
                                 'tooling': str(Path(tooling_dir).resolve()),
                                 'output': 'new external private bundle'}}
    lock['lock_sha256'] = digest(lock)
    validate_contract(lock, 'javascript-template-lock-v1')
    write_json(out / 'template-lock.json', lock)
    write_json(out / 'render-status.json', {'schema_version': '1.0', 'status': 'complete',
                                            'lock_sha256': lock['lock_sha256'],
                                            'resources': hashes})
    return lock

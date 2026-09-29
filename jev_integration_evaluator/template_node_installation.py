"""Offline Linux Node recipe C packaging, distinct from Python wheel installation.

The two effect stages require separately anchored exact plan digests. Neither
stage launches a host, reads a credential, or authorizes a runtime mode.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import signal
import stat
import subprocess
from contextlib import contextmanager
from pathlib import Path

from .contracts import validate_contract
from .io import InputError, digest, file_hash, read_json, write_json
from .integrations import js_lifecycle
from . import __version__
from . import template_js_catalog
from .template_js_catalog import _source_tree

NODE_VERSION = 'v24.18.0'
NPM_VERSION = '11.16.0'
MAX_FILES = 8192
MAX_BYTES = 256_000_000


def _linux() -> None:
    if (platform.system() != 'Linux' or platform.machine().lower() != 'x86_64'
            or os.name == 'nt'):
        raise InputError('Node install profile requires native Linux x86-64')


def _path(value: str, *, directory: bool = False, exists: bool = True) -> Path:
    if type(value) is not str or not Path(value).is_absolute():
        raise InputError('Node install paths must be absolute')
    path = Path(value)
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise InputError('Node install path traverses a symlink')
    path = path.resolve(strict=exists)
    if exists and (not path.is_dir() if directory else not path.is_file()):
        raise InputError('Node install input has wrong file type')
    return path


def _separate(a: Path, b: Path) -> None:
    if a == b or a.is_relative_to(b) or b.is_relative_to(a):
        raise InputError('Node install input and output trees overlap')


def _tree(root: Path) -> dict[str, str]:
    """Bound and hash all owned regular files; reject symlinks and hard links."""
    if root.is_symlink() or not root.is_dir():
        raise InputError('Node install tree invalid')
    rows: dict[str, str] = {}
    total = 0
    device = root.stat().st_dev
    for path in root.rglob('*'):
        info = path.lstat()
        if (stat.S_ISLNK(info.st_mode) or info.st_dev != device
                or os.path.ismount(path) or (not stat.S_ISDIR(info.st_mode)
                                         and not stat.S_ISREG(info.st_mode))):
            raise InputError('Node install tree contains an unsupported file')
        if stat.S_ISDIR(info.st_mode):
            continue
        if info.st_nlink != 1:
            raise InputError('Node install tree contains a hard link')
        total += info.st_size
        if len(rows) >= MAX_FILES or total > MAX_BYTES:
            raise InputError('Node install tree exceeds profile bounds')
        rows[path.relative_to(root).as_posix()] = file_hash(path)
    return dict(sorted(rows.items()))


def _file(root: Path, name: str) -> Path:
    path = root / name
    if (any(item.is_symlink() for item in (path, *path.parents) if item == root or item.is_relative_to(root))
            or not path.is_file() or not path.resolve().is_relative_to(root)
            or path.stat().st_nlink != 1):
        raise InputError('Node install owned file missing or replaced')
    return path


def _toolchain(request: dict, host: Path) -> dict:
    node = _path(request['node'], exists=True)
    npm = _path(request['npm_cli'], exists=True)
    npm_root = npm.parent.parent
    if npm != npm_root / 'bin' / 'npm-cli.js':
        raise InputError('Unsupported npm package launcher layout')
    tooling = _path(request['tooling_directory'], directory=True)
    for path in (node, npm_root, tooling):
        _separate(path, host)
    if not os.access(node, os.X_OK):
        raise InputError('Pinned Node executable is not executable')
    if file_hash(node) != request['node_sha256'] or file_hash(npm) != request['npm_cli_sha256']:
        raise InputError('Pinned Node/npm bytes changed')
    npm_tree_sha256 = digest(_tree(npm_root))
    if npm_tree_sha256 != request['npm_tree_sha256']:
        raise InputError('Pinned npm package modules changed')
    try:
        node_result = subprocess.run([str(node), '--version'], capture_output=True,
                                     text=True, timeout=5, env={'PATH': '/usr/bin:/bin'})
        npm_result = subprocess.run([str(node), str(npm), '--version'], capture_output=True,
                                    text=True, timeout=10, env={'PATH': '/usr/bin:/bin'})
    except (OSError, subprocess.TimeoutExpired):
        raise InputError('Pinned Node/npm unavailable') from None
    if (node_result.returncode or npm_result.returncode
            or node_result.stdout.strip() != NODE_VERSION
            or npm_result.stdout.strip() != NPM_VERSION):
        raise InputError('Unsupported Node/npm version')
    # The existing trusted parser is required even for ESM/CJS lifecycle
    # receipt revalidation. It rejects missing/substituted TypeScript 5.8.3.
    try:
        identity = js_lifecycle._tooling(host, tooling)
    except (OSError, ValueError, KeyError):
        raise InputError('Trusted Node/TypeScript tooling unavailable') from None
    if (identity['node_path'] != str(node) or identity['node_sha256'] != file_hash(node)
            or identity['compiler_version'] != '5.8.3'):
        raise InputError('Trusted Node/TypeScript toolchain differs from pin')
    return {'node': str(node), 'node_sha256': file_hash(node),
            'npm_cli': str(npm), 'npm_cli_sha256': file_hash(npm),
            'npm_root': str(npm_root), 'npm_tree_sha256': npm_tree_sha256,
            'node_version': NODE_VERSION, 'npm_version': NPM_VERSION,
            'tooling': identity}


def _render(request: dict, host: Path, toolchain: dict) -> tuple[dict, dict, dict]:
    directory = _path(request['render_directory'], directory=True)
    _separate(directory, host)
    lock = read_json(_file(directory, 'template-lock.json'))
    validate_contract(lock, 'javascript-template-lock-v1')
    if (lock['lock_sha256'] != digest({k: v for k, v in lock.items() if k != 'lock_sha256'})
            or lock['status'] != 'materialized' or lock['tooling'] != toolchain['tooling']):
        raise InputError('JavaScript render lock or tooling changed')
    marker = read_json(_file(directory, 'render-status.json'))
    if marker != {'schema_version': '1.0', 'status': 'complete',
                  'lock_sha256': lock['lock_sha256'], 'resources': lock['owned_resources']}:
        raise InputError('JavaScript render marker changed')
    for name, expected in lock['owned_resources'].items():
        if file_hash(_file(directory, name)) != expected:
            raise InputError('JavaScript render resource changed')
    source_request = read_json(_file(directory, 'template-request.json'))
    validate_contract(source_request, 'javascript-template-request-v1')
    profile = read_json(_file(directory, 'package-profile.json'))
    if (digest(source_request) != lock['request_sha256'] or profile != lock['package']
            or source_request['format'] != lock['format']
            or read_json(_file(directory, 'template-manifest.json')) != template_js_catalog._manifest()
            or read_json(_file(directory, 'implementation-spec.json')) != source_request['implementation_spec']
            or lock['spec_sha256'] != digest(source_request['implementation_spec'])
            or lock['configuration_sha256'] != source_request['reviewed_configuration_sha256']
            or lock['secret_references_sha256'] != digest(source_request['secret_references'])
            or profile['source_sha256'] != source_request['reviewed_package_source_sha256']
            or lock['source_sha256'] != source_request['implementation_spec']['source']['sha256']
            or lock['manifest_sha256'] != template_js_catalog.inspect_js_template()['manifest_sha256']
            or lock['evaluator_version'] != __version__
            or lock['renderer_sha256'] != file_hash(Path(template_js_catalog.__file__))):
        raise InputError('JavaScript render request or package profile changed')
    if '.npmrc' in profile['source_files']:
        raise InputError('Target npm configuration is unsupported by offline install profile')
    return lock, source_request, profile


def _applied(request: dict, host: Path, source_request: dict, profile: dict,
             toolchain: dict) -> tuple[dict, dict]:
    bundle = _path(request['implementation_bundle'], directory=True)
    _separate(bundle, host)
    if js_lifecycle.status_js(host, bundle, tooling_dir=Path(request['tooling_directory']),
                              trusted_modified_sha256=request['trusted_modified_sha256'])['status'] != 'verified':
        raise InputError('Externally anchored modified JavaScript verification required')
    plan = read_json(_file(bundle, 'plan.json'))
    receipt = read_json(_file(bundle, 'modified-receipt.json'))
    if (file_hash(_file(bundle, 'modified-receipt.json')) != request['trusted_modified_sha256']
            or plan['spec_sha256'] != digest(source_request['implementation_spec'])
            or plan['tooling'] != toolchain['tooling'] or receipt['plan_sha256'] != plan['contract_digest']
            or receipt['status'] != 'passed' or plan['format'] != source_request['format']):
        raise InputError('JavaScript implementation receipt binding changed')
    expected = profile['source_files'].copy()
    expected.update(plan['generated_sha256'])
    actual = _source_tree(host)
    if actual != expected:
        raise InputError('Applied JavaScript package source drift')
    if '.npmrc' in actual:
        raise InputError('Target npm configuration is unsupported by offline install profile')
    if (actual['package.json'] != source_request['package_json_sha256']
            or actual['package-lock.json'] != source_request['package_lock_sha256']
            or actual[source_request['entrypoint']] != expected[source_request['entrypoint']]):
        raise InputError('Reviewed Node package or lock changed')
    current_request = source_request.copy()
    current_request['reviewed_package_source_sha256'] = digest(actual)
    current_request['entrypoint_sha256'] = actual[source_request['entrypoint']]
    current_package = template_js_catalog._package(host, current_request, plan['format'])
    for field in ('name', 'version', 'entrypoint', 'dependency_count',
                  'package_json_sha256', 'package_lock_sha256'):
        if current_package[field] != profile[field]:
            raise InputError('Applied Node package dependency profile changed')
    return plan, actual


def plan_node_package(request: dict, *, _allow_existing_output: bool = False) -> dict:
    """Read-only exact package plan over an already applied and verified host."""
    _linux()
    validate_contract(request, 'node-package-request-v1')
    host = _path(request['host_root'], directory=True)
    cache = _path(request['offline_cache'], directory=True)
    output = _path(request['package_directory'], exists=False)
    if (output.exists() or _intent_path(output).exists()
            or _intent_path(output).with_suffix('.tmp').exists()) and not _allow_existing_output:
        raise InputError('Node package output must be new')
    for item in (host, cache, _path(request['render_directory'], directory=True),
                 _path(request['implementation_bundle'], directory=True),
                 _path(request['tooling_directory'], directory=True)):
        _separate(output, item)
    _separate(cache, host)
    toolchain = _toolchain(request, host)
    _separate(output, Path(toolchain['npm_root']))
    lock, source_request, profile = _render(request, host, toolchain)
    implementation, source_files = _applied(request, host, source_request, profile, toolchain)
    selected = source_request['implementation_spec']['source']['file']
    if (lock['generated_sha256'] != implementation['generated_sha256'][selected]
            or lock['emitted_sha256'] != (implementation['generated_sha256']['host.mjs']
                if lock['format'] == 'typescript' else None)):
        raise InputError('JavaScript generated source differs from render lock')
    cache_files = _tree(cache)
    plan = {'schema_version': '1.0', 'kind': 'node-package-plan-v1',
            'request': request, 'render_lock_sha256': lock['lock_sha256'],
            'implementation_plan_sha256': implementation['contract_digest'],
            'applied_source_files': source_files, 'applied_source_sha256': digest(source_files),
            'offline_cache_sha256': digest(cache_files), 'toolchain': toolchain,
            'configuration_sha256': lock['configuration_sha256'],
            'secret_references_sha256': lock['secret_references_sha256'],
            'package_profile_sha256': digest(profile),
            'format': lock['format'], 'entrypoint': source_request['entrypoint'],
            'mode': 'off', 'runtime_activation_authorized': False}
    plan['plan_sha256'] = digest(plan)
    validate_contract(plan, 'node-package-plan-v1')
    return plan


def _check_plan(plan: dict) -> None:
    validate_contract(plan, 'node-package-plan-v1')
    if plan['plan_sha256'] != digest({k: v for k, v in plan.items() if k != 'plan_sha256'}):
        raise InputError('Node package plan digest changed')
    if plan_node_package(plan['request'], _allow_existing_output=True) != plan:
        raise InputError('Node package source, cache or toolchain drift')


def _safe_new(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise InputError('Node owned output already exists')
    parent = _path(str(path.parent), directory=True)
    info = parent.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
        raise InputError('Node output parent is not privately owned')
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)


def _intent_path(root: Path) -> Path:
    return root.parent / ('.jev-node-intent-' + digest(str(root))[:24] + '.json')


def _intent(root: Path, plan_sha256: str, kind: str, *, create: bool = False) -> bool:
    """Durable parent-side ownership before the generated directory exists."""
    parent = _path(str(root.parent), directory=True)
    info = parent.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
        raise InputError('Node output parent is not privately owned')
    path = _intent_path(root)
    expected = {'schema_version': '1.0', 'kind': kind,
                'plan_sha256': plan_sha256, 'root': str(root)}
    expected['intent_sha256'] = digest(expected)
    if create:
        if root.exists() or root.is_symlink() or path.exists() or path.is_symlink():
            raise InputError('Node owned output already exists')
        temporary = path.with_suffix('.tmp')
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try:
            payload = (json.dumps(expected, sort_keys=True, separators=(',', ':')) + '\n').encode()
            if os.write(fd, payload) != len(payload):
                raise InputError('Node ownership intent write incomplete')
            os.fsync(fd)
        finally:
            os.close(fd)
        if path.exists() or path.is_symlink():
            raise InputError('Node ownership intent collision')
        os.replace(temporary, path)
        parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        return True
    if not path.exists() and not path.is_symlink():
        if path.with_suffix('.tmp').exists() or path.with_suffix('.tmp').is_symlink():
            raise InputError('Node ownership intent precommit incomplete')
        return False
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise InputError('Node ownership intent replaced')
    if read_json(path) != expected:
        raise InputError('Node ownership intent changed')
    return True


def _record(root: Path, plan_sha256: str, event: str) -> str:
    journal = root / 'journal.jsonl'
    rows = _journal(root, plan_sha256)
    previous = rows[-1]['record_sha256'] if rows else None
    row = {'sequence': len(rows), 'previous': previous,
           'plan_sha256': plan_sha256, 'event': event}
    row['record_sha256'] = digest(row)
    with journal.open('ab') as stream:
        stream.write((json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n').encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(journal, 0o600)
    return row['record_sha256']


def _journal(root: Path, plan_sha256: str) -> list[dict]:
    path = root / 'journal.jsonl'
    if not path.exists():
        return []
    _file(root, 'journal.jsonl')
    rows = []
    previous = None
    for line in path.read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        if (type(row) is not dict or set(row) != {'sequence', 'previous', 'plan_sha256',
                                                'event', 'record_sha256'}
                or row['sequence'] != len(rows) or row['previous'] != previous
                or row['plan_sha256'] != plan_sha256
                or row['record_sha256'] != digest({k: v for k, v in row.items()
                                                 if k != 'record_sha256'})):
            raise InputError('Node ownership journal changed')
        previous = row['record_sha256']
        rows.append(row)
    return rows


def _owner(root: Path, plan_sha256: str, kind: str) -> dict:
    marker = read_json(_file(root, 'owner.json'))
    if marker != {'schema_version': '1.0', 'kind': kind,
                  'plan_sha256': plan_sha256, 'root': str(root)}:
        raise InputError('Node owned root marker changed')
    return marker


def _top_level(root: Path, allowed: set[str]) -> None:
    if root.is_symlink() or not root.is_dir():
        raise InputError('Node owned root is not a directory')
    names = {item.name for item in root.iterdir()}
    if not names <= allowed or any(item.is_symlink() for item in root.iterdir()):
        raise InputError('Node owned root contains an unrelated or linked path')


@contextmanager
def _lock(parent: Path, key: str):
    import fcntl
    locks = parent / '.jev-node-locks'
    if not locks.exists():
        locks.mkdir(mode=0o700)
    if (locks.is_symlink() or locks.stat().st_uid != os.getuid()
            or stat.S_IMODE(locks.stat().st_mode) != 0o700):
        raise InputError('Node lock directory unsafe')
    path = locks / (key + '.lock')
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
            raise InputError('Node lock has wrong owner')
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _npm_env(root: Path) -> dict[str, str]:
    home = root / 'home'
    home.mkdir(mode=0o700)
    userconfig = home / '.npmrc'
    userconfig.write_text('', encoding='utf-8')
    os.chmod(userconfig, 0o600)
    globalconfig = home / 'global.npmrc'
    globalconfig.write_text('', encoding='utf-8')
    os.chmod(globalconfig, 0o600)
    return {'PATH': '/usr/bin:/bin', 'HOME': str(home), 'TMPDIR': str(root / 'tmp'),
            'npm_config_cache': str(root / 'cache'),
            'npm_config_userconfig': str(userconfig),
            'npm_config_globalconfig': str(globalconfig),
            'npm_config_ignore_scripts': 'true', 'npm_config_offline': 'true',
            'npm_config_audit': 'false', 'npm_config_fund': 'false',
            'npm_config_update_notifier': 'false'}


def _payload_tree(root: Path) -> dict[str, str]:
    return _tree(root / 'app')


def build_node_package(plan: dict, *, approved_plan_sha256: str) -> dict:
    """Copy reviewed bytes and install from an exact offline cache, no scripts."""
    _linux()
    if approved_plan_sha256 != plan.get('plan_sha256'):
        raise InputError('Exact Node package build approval required')
    _check_plan(plan)
    request = plan['request']
    output = _path(request['package_directory'], exists=False)
    with _lock(output.parent, digest(str(output))):
        _check_plan(plan)
        _intent(output, plan['plan_sha256'], 'node-package-intent-v1', create=True)
        _safe_new(output)
        write_json(output / 'owner.json', {'schema_version': '1.0',
                   'kind': 'node-package-owner-v1', 'plan_sha256': plan['plan_sha256'],
                   'root': str(output)})
        _record(output, plan['plan_sha256'], 'build_started')
        app = output / 'app'
        app.mkdir(mode=0o700)
        host = Path(request['host_root'])
        for name, expected in plan['applied_source_files'].items():
            source = _file(host, name)
            if file_hash(source) != expected:
                raise InputError('Applied Node source changed during copy')
            target = app / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            os.chmod(target, 0o600)
        cache = output / 'cache'
        shutil.copytree(request['offline_cache'], cache, symlinks=True)
        if digest(_tree(cache)) != plan['offline_cache_sha256']:
            raise InputError('Offline npm cache changed during copy')
        npm_tool = output / 'npm_tool'
        shutil.copytree(plan['toolchain']['npm_root'], npm_tool, symlinks=True)
        if digest(_tree(npm_tool)) != plan['toolchain']['npm_tree_sha256']:
            raise InputError('Pinned npm package changed during copy')
        (output / 'tmp').mkdir(mode=0o700)
        env = _npm_env(output)
        node, npm = plan['toolchain']['node'], str(npm_tool / 'bin/npm-cli.js')
        if file_hash(Path(node)) != plan['toolchain']['node_sha256']:
            raise InputError('Pinned Node executable changed before npm effect')
        command = [node, npm, 'ci', '--ignore-scripts', '--offline', '--omit=dev',
                   '--no-audit', '--no-fund', '--cache', str(cache)]
        try:
            process = subprocess.Popen(command, cwd=app, env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       start_new_session=True)
            try:
                returncode = process.wait(timeout=180)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise InputError('Offline npm ci timed out; owned build needs review') from None
        except OSError:
            raise InputError('Offline npm ci failed; owned build needs review') from None
        if returncode:
            # npm diagnostics may contain source or URLs; retain only status.
            raise InputError('Offline npm ci failed; owned build needs review')
        if digest(_tree(npm_tool)) != plan['toolchain']['npm_tree_sha256']:
            raise InputError('Pinned npm tool changed during install')
        built = _payload_tree(output)
        if any(name.endswith(('.node', '.so', '.dll', '.dylib', '.exe')) for name in built):
            raise InputError('Native dependency binary is outside Node install profile')
        if (any(built.get(name) != value for name, value in plan['applied_source_files'].items())
                or built.get(plan['entrypoint']) != plan['applied_source_files'][plan['entrypoint']]):
            raise InputError('npm ci changed reviewed application bytes')
        head = _record(output, plan['plan_sha256'], 'build_complete')
        receipt = {'schema_version': '1.0', 'kind': 'node-package-receipt-v1',
                   'plan_sha256': plan['plan_sha256'], 'package_directory': str(output),
                   'artifact_files': built, 'artifact_sha256': digest(built),
                   'source_sha256': plan['applied_source_sha256'],
                   'configuration_sha256': plan['configuration_sha256'],
                   'secret_references_sha256': plan['secret_references_sha256'],
                   'entrypoint_sha256': built[plan['entrypoint']],
                   'journal_head': head, 'mode': 'off', 'runtime_activation_authorized': False}
        receipt['receipt_sha256'] = digest(receipt)
        validate_contract(receipt, 'node-package-receipt-v1')
        write_json(output / 'package-receipt.json', receipt)
        return receipt


def package_status(plan: dict, *, trusted_receipt_sha256: str | None = None) -> dict:
    _linux()
    _check_plan(plan)
    root = Path(plan['request']['package_directory'])
    has_intent = _intent(root, plan['plan_sha256'], 'node-package-intent-v1')
    if root.is_symlink():
        raise InputError('Node package root is a symlink')
    if not root.exists():
        return {'status': 'build_interrupted_review_required' if has_intent else 'absent',
                'stage': 'intent_recorded' if has_intent else 'none'}
    if not has_intent:
        raise InputError('Node package root has no prior ownership intent')
    _top_level(root, {'owner.json', 'journal.jsonl', 'app', 'cache', 'npm_tool', 'home', 'tmp',
                      'package-receipt.json'})
    if not (root / 'owner.json').is_file():
        if any(root.iterdir()):
            raise InputError('Node markerless package root contains unknown content')
        return {'status': 'build_interrupted_review_required', 'stage': 'directory_created'}
    _owner(root, plan['plan_sha256'], 'node-package-owner-v1')
    rows = _journal(root, plan['plan_sha256'])
    if not rows:
        return {'status': 'build_interrupted_review_required', 'stage': 'owner_marked'}
    if rows[0]['event'] != 'build_started':
        raise InputError('Node package journal missing build start')
    if rows[-1]['event'] != 'build_complete':
        return {'status': 'build_interrupted_review_required', 'journal_head': rows[-1]['record_sha256']}
    if digest(_tree(root / 'npm_tool')) != plan['toolchain']['npm_tree_sha256']:
        raise InputError('Pinned npm package changed after build')
    if not (root / 'package-receipt.json').is_file():
        return {'status': 'build_interrupted_review_required', 'journal_head': rows[-1]['record_sha256']}
    receipt = read_json(_file(root, 'package-receipt.json'))
    validate_contract(receipt, 'node-package-receipt-v1')
    if (receipt['receipt_sha256'] != digest({k: v for k, v in receipt.items()
                                           if k != 'receipt_sha256'})
            or receipt['plan_sha256'] != plan['plan_sha256']
            or receipt['package_directory'] != str(root)
            or receipt['journal_head'] != rows[-1]['record_sha256']
            or receipt['artifact_files'] != _payload_tree(root)
            or receipt['artifact_sha256'] != digest(receipt['artifact_files'])
            or receipt['source_sha256'] != plan['applied_source_sha256']
            or receipt['configuration_sha256'] != plan['configuration_sha256']
            or receipt['secret_references_sha256'] != plan['secret_references_sha256']
            or receipt['entrypoint_sha256'] != receipt['artifact_files'][plan['entrypoint']]):
        raise InputError('Node package artifact or receipt drift')
    return {'status': 'packaged_recorded' if trusted_receipt_sha256 == receipt['receipt_sha256']
            else 'packaged_unanchored', 'receipt_sha256': receipt['receipt_sha256']}


def plan_node_install(package_plan: dict, package_receipt: dict, *,
                      trusted_package_receipt_sha256: str) -> dict:
    """Read-only install plan; an externally retained package receipt is required."""
    _linux()
    validate_contract(package_receipt, 'node-package-receipt-v1')
    if (trusted_package_receipt_sha256 != package_receipt['receipt_sha256']
            or package_status(package_plan,
                              trusted_receipt_sha256=trusted_package_receipt_sha256)['status'] != 'packaged_recorded'):
        raise InputError('Externally anchored Node package receipt required')
    if read_json(Path(package_receipt['package_directory']) / 'package-receipt.json') != package_receipt:
        raise InputError('Node package receipt differs from owned record')
    request = package_plan['request']
    parent = _path(request['environment_parent'], directory=True)
    if parent.stat().st_uid != os.getuid() or stat.S_IMODE(parent.stat().st_mode) & 0o022:
        raise InputError('Node generation parent is not privately owned')
    plan = {'schema_version': '1.0', 'kind': 'node-install-plan-v1',
            'package_plan': package_plan, 'package_receipt': package_receipt,
            'trusted_package_receipt_sha256': trusted_package_receipt_sha256,
            'environment_parent': str(parent), 'mode': 'off',
            'runtime_activation_authorized': False}
    plan['plan_sha256'] = digest(plan)
    root = parent / ('jev-node-env-' + plan['plan_sha256'][:24])
    for key in ('host_root', 'render_directory', 'implementation_bundle',
                'tooling_directory', 'offline_cache', 'package_directory'):
        _separate(root, _path(request[key], directory=True))
    if (root.exists() or root.is_symlink() or _intent_path(root).exists()
            or _intent_path(root).with_suffix('.tmp').exists()):
        raise InputError('Node generation output already exists')
    validate_contract(plan, 'node-install-plan-v1')
    return plan


def _check_install(plan: dict) -> Path:
    validate_contract(plan, 'node-install-plan-v1')
    if plan['plan_sha256'] != digest({k: v for k, v in plan.items() if k != 'plan_sha256'}):
        raise InputError('Node install plan digest changed')
    package_plan = plan['package_plan']
    receipt = plan['package_receipt']
    if (plan['trusted_package_receipt_sha256'] != receipt['receipt_sha256']
            or package_status(package_plan,
                              trusted_receipt_sha256=plan['trusted_package_receipt_sha256'])['status'] != 'packaged_recorded'):
        raise InputError('Node package artifact changed before install')
    parent = _path(plan['environment_parent'], directory=True)
    if parent != _path(package_plan['request']['environment_parent'], directory=True):
        raise InputError('Node generation parent changed')
    root = parent / ('jev-node-env-' + plan['plan_sha256'][:24])
    for key in ('host_root', 'render_directory', 'implementation_bundle',
                'tooling_directory', 'offline_cache', 'package_directory'):
        _separate(root, _path(package_plan['request'][key], directory=True))
    return root


def install_node_package(plan: dict, *, approved_plan_sha256: str) -> dict:
    """Install immutable owned bytes without executing the application."""
    _linux()
    if approved_plan_sha256 != plan.get('plan_sha256'):
        raise InputError('Exact Node install approval required')
    root = _check_install(plan)
    with _lock(root.parent, digest(str(root))):
        _check_install(plan)
        _intent(root, plan['plan_sha256'], 'node-generation-intent-v1', create=True)
        _safe_new(root)
        write_json(root / 'owner.json', {'schema_version': '1.0',
                   'kind': 'node-generation-owner-v1', 'plan_sha256': plan['plan_sha256'],
                   'root': str(root)})
        _record(root, plan['plan_sha256'], 'install_started')
        package = plan['package_receipt']
        shutil.copytree(Path(package['package_directory']) / 'app', root / 'app',
                        symlinks=True)
        installed = _payload_tree(root)
        if installed != package['artifact_files']:
            raise InputError('Node generation copy changed package artifact')
        head = _record(root, plan['plan_sha256'], 'install_complete')
        entrypoint = root / 'app' / plan['package_plan']['entrypoint']
        node = Path(plan['package_plan']['toolchain']['node'])
        generation_id = digest({'plan': plan['plan_sha256'],
                                'artifact': package['artifact_sha256']})
        receipt = {'schema_version': '1.0', 'kind': 'node-install-receipt-v1',
                   'plan_sha256': plan['plan_sha256'], 'generation_id': generation_id,
                   'generation_path': str(root), 'working_directory': str(root / 'app'),
                   'command': [str(node), str(entrypoint)],
                   'executable_sha256': file_hash(node),
                   'entrypoint_sha256': file_hash(entrypoint),
                   'artifact_sha256': package['artifact_sha256'],
                   'source_sha256': package['source_sha256'],
                   'configuration_sha256': package['configuration_sha256'],
                   'secret_references_sha256': package['secret_references_sha256'],
                   'installed_files': installed, 'journal_head': head,
                   'mode': 'off', 'runtime_activation_authorized': False,
                   'launch_status': 'not_started'}
        receipt['receipt_sha256'] = digest(receipt)
        validate_contract(receipt, 'node-install-receipt-v1')
        write_json(root / 'install-receipt.json', receipt)
        return receipt


def installation_status(plan: dict, *, trusted_receipt_sha256: str | None = None) -> dict:
    """Check owned generation bytes; never launch or adopt a running process."""
    _linux()
    root = _check_install(plan)
    has_intent = _intent(root, plan['plan_sha256'], 'node-generation-intent-v1')
    if root.is_symlink():
        raise InputError('Node generation root is a symlink')
    if not root.exists():
        return {'status': 'install_interrupted_review_required' if has_intent else 'absent',
                'stage': 'intent_recorded' if has_intent else 'none'}
    if not has_intent:
        raise InputError('Node generation root has no prior ownership intent')
    _top_level(root, {'owner.json', 'journal.jsonl', 'app', 'install-receipt.json'})
    if not (root / 'owner.json').is_file():
        if any(root.iterdir()):
            raise InputError('Node markerless generation root contains unknown content')
        return {'status': 'install_interrupted_review_required', 'stage': 'directory_created'}
    _owner(root, plan['plan_sha256'], 'node-generation-owner-v1')
    rows = _journal(root, plan['plan_sha256'])
    if not rows:
        return {'status': 'install_interrupted_review_required', 'stage': 'owner_marked'}
    if rows[0]['event'] != 'install_started':
        raise InputError('Node generation journal missing install start')
    if rows[-1]['event'] != 'install_complete':
        return {'status': 'install_interrupted_review_required',
                'journal_head': rows[-1]['record_sha256']}
    if not (root / 'install-receipt.json').is_file():
        return {'status': 'install_interrupted_review_required',
                'journal_head': rows[-1]['record_sha256']}
    receipt = read_json(_file(root, 'install-receipt.json'))
    validate_contract(receipt, 'node-install-receipt-v1')
    package = plan['package_receipt']
    expected_id = digest({'plan': plan['plan_sha256'], 'artifact': package['artifact_sha256']})
    entrypoint = root / 'app' / plan['package_plan']['entrypoint']
    node = Path(plan['package_plan']['toolchain']['node'])
    if (receipt['receipt_sha256'] != digest({k: v for k, v in receipt.items()
                                           if k != 'receipt_sha256'})
            or receipt['plan_sha256'] != plan['plan_sha256']
            or receipt['generation_id'] != expected_id
            or receipt['generation_path'] != str(root)
            or receipt['working_directory'] != str(root / 'app')
            or receipt['command'] != [str(node), str(entrypoint)]
            or receipt['executable_sha256'] != file_hash(node)
            or receipt['entrypoint_sha256'] != file_hash(_file(root / 'app', plan['package_plan']['entrypoint']))
            or receipt['artifact_sha256'] != package['artifact_sha256']
            or receipt['source_sha256'] != package['source_sha256']
            or receipt['configuration_sha256'] != package['configuration_sha256']
            or receipt['secret_references_sha256'] != package['secret_references_sha256']
            or receipt['installed_files'] != _payload_tree(root)
            or receipt['journal_head'] != rows[-1]['record_sha256']
            or receipt['launch_status'] != 'not_started'):
        raise InputError('Node generation artifact or receipt drift')
    return {'status': 'installed_recorded' if trusted_receipt_sha256 == receipt['receipt_sha256']
            else 'installed_unanchored', 'generation_id': expected_id,
            'receipt_sha256': receipt['receipt_sha256'], 'launch_status': 'not_started'}

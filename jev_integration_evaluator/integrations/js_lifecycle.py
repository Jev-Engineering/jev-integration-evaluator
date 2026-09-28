"""Owned, source-bound JS/TS recipe C bundle. No target imports during planning."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from importlib.resources import files

from ..contracts import seal, verify, validate_contract
from ..implementation import make_patch_plan, apply_patch_plan
from ..io import InputError, atomic_text, digest, file_hash, read_json, read_jsonl, safe_child, write_json
from .js_backend import render_js_adapter, transform_js_source, trusted_js_tool_identity

DATA = Path(str(files('jev_integration_evaluator').joinpath('data')))
HEX = re.compile(r'^[0-9a-f]{64}$')
BINDING_ROLES = {'registry', 'gate', 'validate', 'blocked', 'evidence', 'baseline_action'}
FORMATS = {'.mjs': 'esm', '.cjs': 'commonjs', '.ts': 'typescript'}


def _check_spec(spec: dict) -> dict:
    validate_contract(spec, 'javascript-implementation-spec-v1')
    if (type(spec) is not dict or set(spec) != {'schema_version', 'recipe_id', 'candidate_id',
            'source', 'bindings', 'runtime', 'verification_sha256', 'verification_cases_count'} or spec['schema_version'] != '1.0'
            or spec['recipe_id'] != 'javascript.C' or type(spec['candidate_id']) is not str
            or not 1 <= len(spec['candidate_id']) <= 256 or type(spec['source']) is not dict
            or set(spec['source']) != {'file', 'sha256', 'symbol', 'original'}
            or type(spec['source']['file']) is not str
            or not re.fullmatch(r'[A-Za-z_$][\w$-]*\.(mjs|cjs|ts)', spec['source']['file'])
            or type(spec['source']['sha256']) is not str or not HEX.fullmatch(spec['source']['sha256'])
            or type(spec['bindings']) is not dict or set(spec['bindings']) != BINDING_ROLES
            or any(type(x) is not str or not re.fullmatch(r'[A-Za-z_$][\w$]*', x)
                   for x in spec['bindings'].values())
            or len(set(spec['bindings'].values())) != len(BINDING_ROLES)
            or type(spec['verification_sha256']) is not str
            or not HEX.fullmatch(spec['verification_sha256'])
            or type(spec['verification_cases_count']) is not int
            or not 1 <= spec['verification_cases_count'] <= 16):
        raise InputError('Invalid bounded JavaScript implementation specification')
    source = spec['source']
    if (source['symbol'] in spec['bindings'].values() or source['original'] in spec['bindings'].values()
            or source['symbol'] == source['original']):
        raise InputError('JavaScript host binding collision')
    runtime = spec['runtime']
    if (type(runtime) is not dict or set(runtime) != {'registered_action_ids', 'questions',
            'primary_question', 'label_actions', 'runtime'} or type(runtime['runtime']) is not dict
            or runtime['runtime'].get('mode') != 'off'):
        raise InputError('JavaScript runtime must be reviewed and default off')
    registered = runtime['registered_action_ids']
    questions = runtime['questions']
    primary = runtime['primary_question']
    labels = runtime['label_actions']
    settings = runtime['runtime']
    if (len(registered) != len(set(registered)) or type(questions.get(primary)) is not dict
            or questions[primary].get('type') != 'choice'
            or type(questions[primary].get('criteria')) is not dict
            or set(questions[primary]['criteria']) != set(labels)
            or 'uncertain' not in labels or labels['uncertain'] is not None
            or not any(action is None for action in labels.values())
            or any(action is not None and action not in registered for action in labels.values())
            or not 1 <= settings['timeout_ms'] <= 120_000
            or not 0 < settings['cost_upper_bound'] <= 1_000_000
            or re.search(r'(latest|preview)$', settings['model'])):
        raise InputError('Invalid reviewed finite JavaScript runtime contract')
    render_js_adapter(dict(recipe_id='javascript.C', candidate_id=spec['candidate_id'],
                           source_sha256=source['sha256'], **runtime))
    return spec


def _tooling(root: Path, tooling_dir: Path) -> dict:
    tooling = trusted_js_tool_identity(tooling_dir)
    if (Path(tooling['node_path']).is_relative_to(root) or
            Path(tooling['compiler_path']).is_relative_to(root) or DATA.resolve().is_relative_to(root)):
        raise InputError('Trusted JavaScript tooling must remain outside target')
    return tooling


def _root(root: Path) -> Path:
    if sys.platform != 'linux':
        raise InputError('JavaScript owned bundle is supported only on native Linux')
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise InputError('JavaScript target root must be a directory')
    return root


def _bundle(root: Path, bundle: Path) -> Path:
    bundle = Path(bundle).absolute()
    if any(p.is_symlink() for p in (bundle, *bundle.parents)):
        raise InputError('JavaScript bundle path cannot traverse symlinks')
    bundle = bundle.resolve()
    if bundle == root or bundle.is_relative_to(root) or root.is_relative_to(bundle):
        raise InputError('JavaScript bundle must be separate from target')
    return bundle


def _sync_dir(path: Path) -> None:
    handle = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)


@contextmanager
def _lock(bundle: Path):
    if sys.platform != 'linux':
        raise InputError('JavaScript owned bundle is supported only on native Linux')
    import fcntl
    path = safe_child(Path(bundle), 'operation.lock')
    handle = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        if stat.S_IMODE(os.fstat(handle).st_mode) != 0o600:
            raise InputError('Unsafe JavaScript bundle lock mode')
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise InputError('Another JavaScript bundle operation owns the lock') from None
        yield
    finally:
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            os.close(handle)


@contextmanager
def _target_lock(root: Path):
    """Serialize distinct bundles that own the same repository/worktree."""
    target = _root(root)
    import fcntl
    directory = Path(tempfile.gettempdir()) / f'jev-js-target-locks-{os.getuid()}'
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError:
        pass
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise InputError('Unsafe JavaScript target lock directory')
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        name = digest([str(target), target.stat().st_dev, target.stat().st_ino]) + '.lock'
        handle = os.open(name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
        try:
            file_info = os.fstat(handle)
            if file_info.st_uid != os.getuid() or stat.S_IMODE(file_info.st_mode) != 0o600:
                raise InputError('Unsafe JavaScript target lock')
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise InputError('Another JavaScript bundle owns this target') from None
            yield
        finally:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            finally:
                os.close(handle)
    finally:
        os.close(directory_fd)


def _generated(root: Path, spec: dict, tooling_dir: Path) -> tuple[dict, dict]:
    rel = spec['source']['file']
    source = safe_child(root, rel)
    if not source.is_file() or source.is_symlink() or file_hash(source) != spec['source']['sha256']:
        raise InputError('Reviewed JavaScript source changed')
    transformed = transform_js_source(root, rel, symbol=spec['source']['symbol'],
        original=spec['source']['original'], adapter_alias='jevAdapter',
        adapter_path='./jev_adapter.cjs', bindings=spec['bindings'], tooling_dir=tooling_dir)
    if transformed['source_sha256'] != spec['source']['sha256'] or (
            transformed['format'] != FORMATS[source.suffix]):
        raise InputError('Trusted transform changed reviewed source identity')
    adapter_spec = dict(recipe_id='javascript.C', candidate_id=spec['candidate_id'],
                        source_sha256=spec['source']['sha256'], **spec['runtime'])
    changes = {rel: transformed['transformed_source'],
               'jev_adapter.cjs': render_js_adapter(adapter_spec),
               'jev_runtime.cjs': (DATA / 'native_js_runtime.cjs').read_text(encoding='utf-8')}
    if transformed['format'] == 'typescript':
        changes['host.mjs'] = transformed['emitted_source']
    for path in set(changes) - {rel}:
        if safe_child(root, path).exists():
            raise InputError('Generated JavaScript output collides with existing host path')
    return transformed, changes


def _append(bundle: Path, plan: dict, event: str) -> None:
    path = bundle / 'journal.jsonl'
    rows = list(read_jsonl(path)) if path.exists() else []
    previous = None
    for i, row in enumerate(rows):
        verify(row)
        if row['sequence'] != i or row['previous'] != previous or row['plan_sha256'] != plan['contract_digest']:
            raise InputError('JavaScript recovery journal changed')
        previous = row['contract_digest']
    row = seal(dict(sequence=len(rows), previous=previous, plan_sha256=plan['contract_digest'], event=event))
    with path.open('ab') as stream:
        stream.write((json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n').encode())
        stream.flush(); os.fsync(stream.fileno())
    _sync_dir(bundle)


def _events(bundle: Path, plan: dict) -> list[str]:
    path = bundle / 'journal.jsonl'
    rows = list(read_jsonl(path)) if path.exists() else []
    previous = None
    for i, row in enumerate(rows):
        verify(row)
        if (set(row) != {'sequence', 'previous', 'plan_sha256', 'event', 'contract_digest'}
                or row['sequence'] != i or row['previous'] != previous
                or row['plan_sha256'] != plan['contract_digest']):
            raise InputError('JavaScript recovery journal changed')
        previous = row['contract_digest']
    return [row['event'] for row in rows]


def plan_js(root: Path, spec: dict, bundle: Path, *, tooling_dir: Path) -> dict:
    with _target_lock(root):
        return _plan_js_unlocked(root, spec, bundle, tooling_dir=tooling_dir)


def _plan_js_unlocked(root: Path, spec: dict, bundle: Path, *, tooling_dir: Path) -> dict:
    root = _root(root); bundle = _bundle(root, bundle); spec = _check_spec(spec)
    if bundle.exists():
        raise InputError('JavaScript bundle output must be new')
    tooling = _tooling(root, tooling_dir)
    transformed, changes = _generated(root, spec, tooling_dir)
    patch = make_patch_plan(root, [{'file': path, 'new_content': value}
                                   for path, value in changes.items()], [spec['candidate_id']])
    source = safe_child(root, spec['source']['file'])
    preimage = source.read_bytes()
    if hashlib.sha256(preimage).hexdigest() != spec['source']['sha256']:
        raise InputError('Reviewed JavaScript source changed during planning')
    bundle.mkdir(mode=0o700, parents=False)
    os.chmod(bundle, 0o700)
    lock_fd = os.open(bundle / 'operation.lock', os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    os.close(lock_fd)
    atomic_text(bundle / 'source-preimage.utf8', preimage.decode('utf-8'))
    os.chmod(bundle / 'source-preimage.utf8', 0o600)
    write_json(bundle / 'spec.json', spec)
    write_json(bundle / 'patch.json', patch)
    plan = seal(dict(schema_version='1.0', kind='javascript-implementation-plan-v1',
                     root_sha256=digest(str(root)), root_device=root.stat().st_dev,
                     root_inode=root.stat().st_ino, spec_sha256=digest(spec),
                     patch_sha256=digest(patch), spec_file_sha256=file_hash(bundle / 'spec.json'),
                     patch_file_sha256=file_hash(bundle / 'patch.json'),
                     preimage_sha256=hashlib.sha256(preimage).hexdigest(),
                     tooling=tooling, format=transformed['format'],
                     generated_sha256={path: hashlib.sha256(value.encode()).hexdigest()
                                       for path, value in changes.items()},
                     owned_files=[dict(file=row['file'], old_sha256=row['old_sha256'],
                                       new_sha256=row['new_sha256'],
                                       old_mode=stat.S_IMODE(safe_child(root, row['file']).stat().st_mode)
                                       if safe_child(root, row['file']).exists() else None)
                                  for row in patch['changes']]))
    write_json(bundle / 'plan.json', plan)
    validate_contract(plan, 'javascript-implementation-plan-v1')
    _sync_dir(bundle)
    _append(bundle, plan, 'planned')
    return dict(status='planned', bundle_sha256=plan['contract_digest'],
                patch_sha256=patch['plan_digest'], target_executed=False,
                target_modified=False, format=plan['format'])


def _load(root: Path, bundle: Path, tooling_dir: Path) -> tuple[Path, Path, dict, dict, dict]:
    root = _root(root); bundle = _bundle(root, bundle)
    plan = read_json(bundle / 'plan.json'); verify(plan)
    validate_contract(plan, 'javascript-implementation-plan-v1')
    spec = _check_spec(read_json(bundle / 'spec.json'))
    patch = read_json(bundle / 'patch.json')
    if (plan['kind'] != 'javascript-implementation-plan-v1' or
            (plan['root_sha256'], plan['root_device'], plan['root_inode']) !=
            (digest(str(root)), root.stat().st_dev, root.stat().st_ino) or
            plan['spec_sha256'] != digest(spec) or plan['patch_sha256'] != digest(patch) or
            plan['spec_file_sha256'] != file_hash(bundle / 'spec.json') or
            plan['patch_file_sha256'] != file_hash(bundle / 'patch.json') or
            plan['tooling'] != _tooling(root, tooling_dir) or
            plan['preimage_sha256'] != file_hash(bundle / 'source-preimage.utf8') or
            patch['plan_digest'] != digest({k: v for k, v in patch.items() if k != 'plan_digest'})):
        raise InputError('JavaScript bundle or trusted tooling changed')
    with tempfile.TemporaryDirectory(prefix='jev-js-regenerate-') as temporary:
        scratch = Path(temporary)
        shutil.copyfile(bundle / 'source-preimage.utf8', scratch / spec['source']['file'])
        _, regenerated = _generated(scratch, spec, tooling_dir)
    if (plan['generated_sha256'] != {path: hashlib.sha256(value.encode()).hexdigest()
                                    for path, value in regenerated.items()} or
            {row['file']: row['new_sha256'] for row in patch['changes']} != plan['generated_sha256'] or
            {row['file'] for row in plan['owned_files']} != set(plan['generated_sha256']) or
            len(plan['owned_files']) != len(plan['generated_sha256']) or
            any(row['new_sha256'] != plan['generated_sha256'][row['file']]
                for row in plan['owned_files'])):
        raise InputError('JavaScript generated bytes differ from archived preimage')
    _events(bundle, plan)
    return root, bundle, plan, spec, patch


def _states(root: Path, plan: dict) -> dict[str, str]:
    found = {}
    for row in plan['owned_files']:
        path = safe_child(root, row['file'])
        actual = file_hash(path) if path.is_file() else None
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
        if actual == row['old_sha256'] and mode == row['old_mode']:
            found[row['file']] = 'baseline'
        elif actual == row['new_sha256'] and mode == (row['old_mode'] if row['old_mode'] is not None
                                                     else (0o666 if os.name == 'nt' else 0o600)):
            found[row['file']] = 'applied'
        else:
            found[row['file']] = 'drift'
    return found


def _receipt(bundle: Path, plan: dict, phase: str, anchor: str | None = None) -> dict:
    path = bundle / (phase + '-receipt.json')
    if anchor is not None and file_hash(path) != anchor:
        raise InputError('JavaScript receipt differs from external digest')
    row = read_json(path); verify(row)
    validate_contract(row, 'javascript-entrypoint-receipt-v1')
    spec = read_json(bundle / 'spec.json')
    if phase == 'baseline':
        if plan['format'] == 'typescript':
            with tempfile.TemporaryDirectory(prefix='jev-js-receipt-source-') as temporary:
                path = Path(temporary) / spec['source']['file']
                shutil.copyfile(bundle / 'source-preimage.utf8', path)
                expected_source = hashlib.sha256(_baseline_ts(path, plan).encode()).hexdigest()
        else:
            expected_source = plan['preimage_sha256']
    else:
        expected_source = plan['generated_sha256'][
            'host.mjs' if plan['format'] == 'typescript' else spec['source']['file']]
    if (row['plan_sha256'] != plan['contract_digest'] or row['phase'] != phase
            or row['cases_sha256'] != spec['verification_sha256']
            or row['source_sha256'] != expected_source
            or row['scheduled'] != spec['verification_cases_count']
            or (row['status'] == 'passed' and row['scheduled'] != row['observed'])):
        raise InputError('JavaScript receipt belongs to another plan or phase')
    return row


def _cases(value: list, spec: dict) -> list:
    if (type(value) is not list or len(value) != spec['verification_cases_count']
            or digest(value) != spec['verification_sha256']):
        raise InputError('Exact externally retained JavaScript verification cases required')
    ids = set()
    for item in value:
        if (type(item) is not dict or set(item) != {'id', 'request', 'result', 'events', 'effects'}
                or type(item['id']) is not str or not item['id'] or item['id'] in ids
                or type(item['request']) is not dict or type(item['events']) is not list
                or type(item['effects']) is not list or not item['effects']):
            raise InputError('Invalid JavaScript verification case')
        ids.add(item['id'])
    return value


def _baseline_ts(source: Path, plan: dict) -> str:
    env = {k: v for k, v in os.environ.items() if k.upper() not in {'NODE_PATH', 'NODE_OPTIONS'}}
    env['JEV_TRUSTED_TYPESCRIPT'] = plan['tooling']['compiler_path']
    done = subprocess.run([plan['tooling']['node_path'], str(DATA / 'js_emit.cjs')],
        input=json.dumps(dict(file=source.name, source=source.read_text(encoding='utf-8'))),
        cwd=DATA, env=env, capture_output=True, text=True, timeout=15, check=False)
    if done.returncode or len(done.stdout) > 1_000_000:
        raise InputError('Trusted TypeScript baseline emit failed')
    out = json.loads(done.stdout)
    if hashlib.sha256(out['source'].encode()).hexdigest() != out['sha256']:
        raise InputError('Trusted TypeScript baseline emit invalid')
    return out['source']


def _probe_run(root: Path, plan: dict, request: dict) -> dict:
    """Bound stdout/stderr and kill the process group on timeout."""
    import resource
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in {'NODE_PATH', 'NODE_OPTIONS', 'NPM_CONFIG_USERCONFIG'}
           and not re.search(r'(?i)(api.?key|secret|password|token)', k)}
    def limit_output():
        resource.setrlimit(resource.RLIMIT_FSIZE, (200_000, 200_000))
    with tempfile.TemporaryFile(mode='w+t', encoding='utf-8') as output, \
            tempfile.TemporaryFile(mode='w+t', encoding='utf-8') as errors:
        process = subprocess.Popen([plan['tooling']['node_path'], str(DATA / 'js_probe.cjs')],
            stdin=subprocess.PIPE, stdout=output, stderr=errors, cwd=root, env=env,
            text=True, start_new_session=True, preexec_fn=limit_output)
        try:
            process.communicate(json.dumps(request), timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise InputError('Reviewed JavaScript entrypoint verification timed out') from None
        output.seek(0)
        raw = output.read(200_001)
        if process.returncode or len(raw) > 200_000:
            raise InputError('Reviewed JavaScript entrypoint verification failed')
    try:
        result = json.loads(raw)
        if type(result) is not dict or set(result) != {'results'} or type(result['results']) is not list:
            raise ValueError('shape')
        return result
    except (ValueError, TypeError):
        raise InputError('Reviewed JavaScript entrypoint observation invalid') from None


def _verify_js_unlocked(root: Path, bundle: Path, phase: str, cases: list, *, tooling_dir: Path,
              approve_execution: bool = False, baseline_sha256: str | None = None) -> dict:
    if not approve_execution:
        raise InputError('Executing JavaScript host requires explicit authorization')
    root, bundle, plan, spec, _ = _load(root, bundle, tooling_dir)
    cases = _cases(cases, spec)
    if phase not in ('baseline', 'modified'):
        raise InputError('Unsupported JavaScript verification phase')
    events = _events(bundle, plan)
    if events[-1] not in ('planned', 'applied_unverified') or (phase == 'baseline') != (events[-1] == 'planned'):
        raise InputError('JavaScript verification requires explicit recovery or correct phase')
    if phase == 'modified':
        if baseline_sha256 is None or _receipt(bundle, plan, 'baseline', baseline_sha256)['status'] != 'passed':
            raise InputError('Externally anchored passing baseline required')
    if set(_states(root, plan).values()) != ({'baseline'} if phase == 'baseline' else {'applied'}):
        raise InputError('JavaScript source or owned files drifted before execution')
    _append(bundle, plan, phase + '_started')
    module = safe_child(root, spec['source']['file'] if phase == 'baseline' or plan['format'] != 'typescript' else 'host.mjs')
    temporary = None
    try:
        if phase == 'baseline' and plan['format'] == 'typescript':
            temporary = tempfile.TemporaryDirectory(prefix='jev-js-baseline-')
            module = Path(temporary.name) / 'host.mjs'
            module.write_text(_baseline_ts(safe_child(root, spec['source']['file']), plan), encoding='utf-8')
        request = dict(module=str(module), format='commonjs' if plan['format'] == 'commonjs' else 'esm',
                       symbol=spec['source']['symbol'], cases=[dict(id=c['id'], request=c['request']) for c in cases])
        observed = _probe_run(root, plan, request)['results']
        if set(_states(root, plan).values()) != ({'baseline'} if phase == 'baseline' else {'applied'}):
            raise InputError('JavaScript host changed owned source during verification')
        expected = [dict(id=c['id'], result=c['result'], exception=None,
                         events=c['events'], effects=c['effects']) for c in cases]
        passed = observed == expected
        receipt = seal(dict(schema_version='1.0', kind='javascript-entrypoint-receipt-v1',
                            phase=phase, plan_sha256=plan['contract_digest'],
                            cases_sha256=spec['verification_sha256'], status='passed' if passed else 'failed',
                            scheduled=len(cases), observed=len(observed),
                            observation_sha256=digest(observed),
                            source_sha256=file_hash(module)))
        validate_contract(receipt, 'javascript-entrypoint-receipt-v1')
        write_json(bundle / (phase + '-receipt.json'), receipt)
        _append(bundle, plan, phase + ('_passed' if passed else '_failed'))
        return dict(status=receipt['status'], phase=phase, receipt_sha256=file_hash(bundle / (phase + '-receipt.json')),
                    scheduled=len(cases), observed=len(observed), target_executed=True)
    finally:
        if temporary is not None:
            temporary.cleanup()


def _apply_js_unlocked(root: Path, bundle: Path, approval: str, *, baseline_sha256: str,
             tooling_dir: Path) -> dict:
    root, bundle, plan, spec, patch = _load(root, bundle, tooling_dir)
    if approval != plan['contract_digest'] or _events(bundle, plan)[-1] != 'baseline_passed':
        raise InputError('Exact reviewed JavaScript bundle approval and baseline required')
    if _receipt(bundle, plan, 'baseline', baseline_sha256)['status'] != 'passed':
        raise InputError('Passing externally anchored JavaScript baseline required')
    if set(_states(root, plan).values()) != {'baseline'}:
        raise InputError('JavaScript source drift before apply')
    _append(bundle, plan, 'apply_started')
    apply_patch_plan(root, patch, patch['plan_digest'])
    for row in plan['owned_files']:
        if row['old_mode'] is None:
            os.chmod(safe_child(root, row['file']), 0o666 if os.name == 'nt' else 0o600)
        _sync_dir(safe_child(root, row['file']).parent)
    if set(_states(root, plan).values()) != {'applied'}:
        raise InputError('JavaScript applied file identity invalid; recover or rollback')
    _append(bundle, plan, 'applied_unverified')
    return dict(status='applied_unverified', bundle_sha256=plan['contract_digest'], target_modified=True)


def _status_js_unlocked(root: Path, bundle: Path, *, tooling_dir: Path,
              trusted_modified_sha256: str | None = None) -> dict:
    root, bundle, plan, _, _ = _load(root, bundle, tooling_dir)
    events = _events(bundle, plan); states = _states(root, plan)
    last = events[-1]
    if last in ('baseline_passed', 'baseline_failed', 'modified_passed', 'modified_failed'):
        _receipt(bundle, plan, 'baseline' if last.startswith('baseline') else 'modified')
    status = ('blocked_recovery' if last.endswith('_started') or 'drift' in states.values()
              else 'rolled_back' if last == 'rolled_back' and set(states.values()) == {'baseline'}
              else 'verification_failed' if last in ('baseline_failed', 'modified_failed')
              else 'planned' if set(states.values()) == {'baseline'}
              else 'applied_unverified' if set(states.values()) == {'applied'}
              else 'blocked_recovery')
    trust = 'absent'
    if status == 'applied_unverified' and last == 'modified_passed':
        trust = 'integrity_consistent_but_unverified'
        if trusted_modified_sha256:
            receipt = _receipt(bundle, plan, 'modified', trusted_modified_sha256)
            if receipt['status'] == 'passed':
                status, trust = 'verified', 'externally_anchored_execution'
    return dict(status=status, file_identity=states, receipt_trust=trust,
                rollback_digest=digest(dict(operation='rollback_js', plan_sha256=plan['contract_digest'],
                                            owned_files=plan['owned_files'])),
                target_executed=False, runtime_activation_authorized=False)


def _recover_js_unlocked(root: Path, bundle: Path, operation: str, *, tooling_dir: Path,
               trusted_receipt_sha256: str | None = None) -> dict:
    root, bundle, plan, _, _ = _load(root, bundle, tooling_dir)
    if _events(bundle, plan)[-1] != operation + '_started':
        raise InputError('No matching interrupted JavaScript operation')
    states = set(_states(root, plan).values())
    if operation in ('baseline', 'modified'):
        if trusted_receipt_sha256 is None or _receipt(bundle, plan, operation, trusted_receipt_sha256)['status'] != 'passed':
            raise InputError('Exact external JavaScript recovery receipt required')
        if states != ({'baseline'} if operation == 'baseline' else {'applied'}):
            raise InputError('Owned source changed during JavaScript recovery')
        _append(bundle, plan, operation + '_passed')
    elif operation == 'apply':
        if states != {'applied'}:
            raise InputError('Partial JavaScript apply requires exact owned rollback')
        _append(bundle, plan, 'applied_unverified')
    else:
        raise InputError('Unsupported JavaScript recovery operation')
    return _status_js_unlocked(root, bundle, tooling_dir=tooling_dir)


def _rollback_js_unlocked(root: Path, bundle: Path, approval: str, *, tooling_dir: Path) -> dict:
    root, bundle, plan, _, _ = _load(root, bundle, tooling_dir)
    expected = digest(dict(operation='rollback_js', plan_sha256=plan['contract_digest'],
                           owned_files=plan['owned_files']))
    if approval != expected:
        raise InputError('Exact reviewed JavaScript rollback digest required')
    states = _states(root, plan)
    if 'drift' in states.values():
        raise InputError('JavaScript rollback refuses concurrent owned edits')
    _append(bundle, plan, 'rollback_started')
    for row in reversed(plan['owned_files']):
        if states[row['file']] != 'applied':
            continue
        path = safe_child(root, row['file'])
        if file_hash(path) != row['new_sha256']:
            raise InputError('Concurrent JavaScript owned edit during rollback')
        if row['old_sha256'] is None:
            path.unlink()
        else:
            preimage = (bundle / 'source-preimage.utf8').read_text(encoding='utf-8')
            atomic_text(path, preimage)
            os.chmod(path, row['old_mode'])
        _sync_dir(path.parent)
    if set(_states(root, plan).values()) != {'baseline'}:
        raise InputError('JavaScript rollback incomplete')
    _append(bundle, plan, 'rolled_back')
    return dict(status='rolled_back', owned_changes_restored=sum(x == 'applied' for x in states.values()),
                unrelated_paths_modified=False)


def verify_js(root: Path, bundle: Path, phase: str, cases: list, *, tooling_dir: Path,
              approve_execution: bool = False, baseline_sha256: str | None = None) -> dict:
    with _lock(bundle), _target_lock(root):
        return _verify_js_unlocked(root, bundle, phase, cases, tooling_dir=tooling_dir,
                                   approve_execution=approve_execution, baseline_sha256=baseline_sha256)


def apply_js(root: Path, bundle: Path, approval: str, *, baseline_sha256: str,
             tooling_dir: Path) -> dict:
    with _lock(bundle), _target_lock(root):
        return _apply_js_unlocked(root, bundle, approval, baseline_sha256=baseline_sha256,
                                  tooling_dir=tooling_dir)


def status_js(root: Path, bundle: Path, *, tooling_dir: Path,
              trusted_modified_sha256: str | None = None) -> dict:
    with _lock(bundle), _target_lock(root):
        return _status_js_unlocked(root, bundle, tooling_dir=tooling_dir,
                                   trusted_modified_sha256=trusted_modified_sha256)


def recover_js(root: Path, bundle: Path, operation: str, *, tooling_dir: Path,
               trusted_receipt_sha256: str | None = None) -> dict:
    with _lock(bundle), _target_lock(root):
        return _recover_js_unlocked(root, bundle, operation, tooling_dir=tooling_dir,
                                    trusted_receipt_sha256=trusted_receipt_sha256)


def rollback_js(root: Path, bundle: Path, approval: str, *, tooling_dir: Path) -> dict:
    with _lock(bundle), _target_lock(root):
        return _rollback_js_unlocked(root, bundle, approval, tooling_dir=tooling_dir)

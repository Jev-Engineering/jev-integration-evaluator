"""Read-only qualification report for the Python recipe C registered-tool template.

The gate list below is the single source for the support matrix in
``references/registered-tool-template-quickstart-v1.md`` and for the report
written by ``scripts/run_registered_tool_qualification.py``. The report is
recomputed from one caller-supplied pytest JUnit XML file. This module never
imports or executes a target, never opens a network connection and cannot
promote a gate that needs authentic provider, canary, active or benefit
evidence. Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path

KIND = 'registered-tool-qualification-report-v1'
TEMPLATE = 'python.bounded-tail-call@1.0.0'
RECIPE = 'python.C@1.0'
PROFILE = 'linux-x86_64-cpython-3.13-single-process-console'
QUALIFIED = 'qualified_offline_synthetic'
UNQUALIFIED = 'implemented_unqualified'
PENDING = 'pending'
PENDING_STATUS = 'pending_authentic_evidence'
OFFLINE_STATUSES = ('passed', 'failed', 'unrun')
MAX_JUNIT_BYTES = 64 * 1024 * 1024
# These gates need authentic observed evidence. No JUnit case can satisfy them.
AUTHENTIC_GATES = ('provider_operation', 'authorized_canary', 'authorized_active',
                   'measured_benefit')
LIMITS = (
    'The JUnit file is caller supplied and unauthenticated; this report is not an approval.',
    'A deselected case leaves no JUnit row; compare the per-module case counts with the retained run.',
    'JUnit does not identify the interpreter or platform; record them separately.',
    'A passed offline gate is offline synthetic fixture evidence, not provider operation or benefit.',
)


def _gate(gate_id: str, title: str, documented_status: str, *modules: str) -> dict:
    return {'id': gate_id, 'title': title,
            'kind': 'authentic' if gate_id in AUTHENTIC_GATES else 'offline',
            'documented_status': documented_status, 'required_modules': tuple(modules)}


GATES = (
    _gate('template_materialize', 'Catalog validation and materialized planner inputs',
          QUALIFIED, 'tests/test_template_catalog.py'),
    _gate('entrypoint_bind', 'Console entrypoint binding and owned entrypoint edit',
          QUALIFIED, 'tests/test_template_python_entrypoint.py'),
    _gate('source_plan_verify_apply_rollback',
          'Source plan, baseline and modified verification, reviewed apply and owned rollback',
          QUALIFIED, 'tests/test_executable_recipes.py', 'tests/test_package_lifecycle.py'),
    _gate('package_install', 'Offline package plan/build and install plan/install',
          QUALIFIED, 'tests/test_template_installation.py'),
    _gate('delivery_session_off',
          'Off-mode delivery session: configure, launch, status, observe, stop, disable, upgrade, rollback',
          QUALIFIED, 'tests/test_template_delivery_session.py',
          'tests/test_template_delivery_installed.py'),
    _gate('independent_host_installed_journey',
          'Independent Alpha host installed journey with controlled faults',
          QUALIFIED, 'tests/test_registered_alpha_oracle.py',
          'tests/test_registered_alpha_installed_faults.py'),
    _gate('installed_upgrade_rollback',
          'Independent Alpha host versioned upgrade and retained generation rollback',
          QUALIFIED, 'tests/test_registered_alpha_installed_upgrade.py'),
    _gate('second_independent_host', 'Second independently authored work-queue host',
          QUALIFIED, 'tests/test_work_queue_oracle.py', 'tests/test_work_queue_installed.py'),
    _gate('composite_two_placements',
          'Two registered placements under one task and shared budget',
          QUALIFIED, 'tests/test_registered_dual_composite.py'),
    _gate('connected_shadow_local_protocol',
          'Installed binding and connected shadow against a local synthetic TLS protocol',
          QUALIFIED, 'tests/test_connected_installed_binding.py',
          'tests/test_connected_loader_public_keys.py'),
    _gate('connected_generation_transfer',
          'Stopped connected generation transfer and signed reverse transfer',
          UNQUALIFIED, 'tests/test_connected_generation_controller.py',
          'tests/test_connected_generation_ledger.py',
          'tests/test_connected_generation_installed.py'),
    _gate('provider_operation', 'Authentic provider endpoint operation', PENDING),
    _gate('authorized_canary', 'Authorized canary with raw observed gate evidence', PENDING),
    _gate('authorized_active', 'Authorized active with raw observed gate evidence', PENDING),
    _gate('measured_benefit', 'Independently measured task benefit', PENDING),
)


class QualificationError(Exception):
    """Fixed diagnostic; no input content is included."""


def _check_gates() -> None:
    ids = [gate['id'] for gate in GATES]
    if len(set(ids)) != len(ids) or not set(AUTHENTIC_GATES) <= set(ids):
        raise QualificationError('qualification_gate_list_invalid')
    for gate in GATES:
        authentic = gate['kind'] == 'authentic'
        if (authentic != (gate['documented_status'] == PENDING)
                or authentic == bool(gate['required_modules'])
                or len(set(gate['required_modules'])) != len(gate['required_modules'])):
            raise QualificationError('qualification_gate_list_invalid')


_check_gates()


def _module_name(module: str) -> str:
    return module.removesuffix('.py').replace('/', '.')


def read_junit(path: str | Path) -> tuple[str, list[dict]]:
    """Return the file digest and one row per testcase without interpreting names."""
    source = Path(path)
    try:
        if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_JUNIT_BYTES:
            raise QualificationError('junit_report_unavailable_or_oversize')
        raw = source.read_bytes()
    except OSError:
        raise QualificationError('junit_report_unavailable_or_oversize') from None
    # pytest never emits a document type; refusing one avoids entity expansion.
    if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:
        raise QualificationError('junit_report_declares_unsupported_markup')
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        raise QualificationError('junit_report_malformed') from None
    if root.tag not in ('testsuites', 'testsuite'):
        raise QualificationError('junit_report_malformed')
    cases = []
    for case in root.iter('testcase'):
        children = {child.tag for child in case}
        outcome = ('failed' if children & {'failure', 'error'} else
                   'skipped' if 'skipped' in children else 'passed')
        cases.append({'classname': case.get('classname') or '', 'name': case.get('name') or '',
                      'outcome': outcome})
    return hashlib.sha256(raw).hexdigest(), cases


def _module_row(module: str, cases: list[dict]) -> dict:
    dotted = _module_name(module)
    counts = {'passed': 0, 'failed': 0, 'skipped': 0}
    for case in cases:
        classname = case['classname']
        # A module-level skip or collection error has no classname and is named after the module.
        if (classname == dotted or classname.startswith(dotted + '.')
                or (not classname and case['name'] in (dotted, module))):
            counts[case['outcome']] += 1
    return {'module': module, 'cases': sum(counts.values()), **counts}


def build_report(junit_sha256: str, cases: list[dict]) -> dict:
    gates = []
    for gate in GATES:
        modules = [_module_row(module, cases) for module in gate['required_modules']]
        if gate['kind'] == 'authentic':
            # Deliberately independent of every JUnit row.
            status, modules = PENDING_STATUS, []
        elif any(row['failed'] for row in modules):
            status = 'failed'
        elif any(row['cases'] == 0 or row['skipped'] for row in modules):
            status = 'unrun'
        else:
            status = 'passed'
        gates.append({'id': gate['id'], 'title': gate['title'], 'kind': gate['kind'],
                      'documented_status': gate['documented_status'],
                      'required_modules': list(gate['required_modules']),
                      'status': status, 'modules': modules})
    listed = {status: [gate['id'] for gate in gates if gate['status'] == status]
              for status in (*OFFLINE_STATUSES, PENDING_STATUS)}
    offline = [gate for gate in gates if gate['kind'] == 'offline']
    outcomes = {name: sum(case['outcome'] == name for case in cases)
                for name in ('passed', 'failed', 'skipped')}
    return {
        'schema_version': '1.0', 'kind': KIND, 'template': TEMPLATE, 'recipe': RECIPE,
        'profile': PROFILE, 'evidence_type': 'offline_synthetic_junit',
        'junit': {'sha256': junit_sha256, 'trust': 'caller_supplied_unauthenticated',
                  'testcases': len(cases), **outcomes},
        'gates': gates,
        'summary': {
            # Every declared gate stays in the denominator, including pending ones.
            'gate_count': len(gates), 'offline_gate_count': len(offline),
            'passed': len(listed['passed']), 'failed': len(listed['failed']),
            'unrun': len(listed['unrun']),
            'pending_authentic_evidence': len(listed[PENDING_STATUS]),
            'passed_gates': listed['passed'], 'failed_gates': listed['failed'],
            'unrun_gates': listed['unrun'], 'pending_gates': listed[PENDING_STATUS],
            'offline_complete': all(gate['status'] == 'passed' for gate in offline),
            'qualification_complete': False},
        'target_code_executed': False, 'network_requests': 0,
        'provider_qualification': 'not_run', 'observed_benefit': False,
        'limits': list(LIMITS)}


def _protected_root() -> Path:
    """The checkout (or installed site directory) that must not receive a report."""
    return Path(__file__).resolve().parents[1]


def write_report_exclusive(path: str | Path, report: dict) -> Path:
    target = Path(path)
    if not target.is_absolute():
        target = Path.cwd() / target
    if target.is_symlink() or any(parent.is_symlink() for parent in target.parents):
        raise QualificationError('report_path_must_not_traverse_symlinks')
    try:
        parent = target.parent.resolve(strict=True)
    except OSError:
        raise QualificationError('report_parent_directory_required') from None
    if not parent.is_dir():
        raise QualificationError('report_parent_directory_required')
    resolved = parent / target.name
    root = _protected_root()
    if resolved == root or resolved.is_relative_to(root):
        raise QualificationError('report_must_be_outside_the_checkout')
    data = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')
    try:
        descriptor = os.open(resolved, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | getattr(os, 'O_BINARY', 0), 0o600)
    except FileExistsError:
        raise QualificationError('report_output_already_exists') from None
    except OSError:
        raise QualificationError('report_output_unavailable') from None
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return resolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='run_registered_tool_qualification.py',
        description='Recompute the registered-tool template gate report from one pytest '
                    'JUnit XML file. Runs no test, target or network call; exit 0 only '
                    'means the report was written.')
    parser.add_argument('--junit', required=True, help='Existing pytest JUnit XML report')
    parser.add_argument('--out', required=True,
                        help='New JSON report file outside the checkout; never overwritten')
    parser.add_argument('--require-offline-complete', action='store_true',
                        help='Exit 3 unless every offline gate is passed; pending gates stay pending')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_report(*read_junit(args.junit))
        write_report_exclusive(args.out, report)
    except QualificationError as exc:
        print(json.dumps({'schema_version': '1.0', 'status': 'rejected', 'reason': str(exc)}),
              file=sys.stderr)
        return 2
    summary = report['summary']
    print(json.dumps({'schema_version': '1.0', 'status': 'report_written',
                      **{name: summary[name] for name in (
                          'gate_count', 'passed', 'failed', 'unrun',
                          'pending_authentic_evidence', 'offline_complete',
                          'qualification_complete')}}, indent=2))
    if args.require_offline_complete and not summary['offline_complete']:
        return 3
    return 0

"""Finite native Windows installed connected CLI; no issuer private key input."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

from . import capabilities as cap
from .io import InputError, loads
from .windows_template_connected_binding import derive_windows_installed_binding
from .windows_template_connected_delivery import (
    plan_windows_connected_delivery, create_windows_connected_session,
    launch_windows_connected_session, windows_connected_session_status,
    observe_windows_connected_session, stop_windows_connected_session,
)
from .windows_template_owned import (
    create_private_directory, write_private_json_exclusive,
)


def _json(path: str) -> dict:
    try:
        value = loads(cap._windows_secure_input(Path(path), 4_000_000))
        if type(value) is not dict:
            raise ValueError('object')
        return value
    except (OSError, ValueError, cap.CapabilityError):
        raise InputError('windows_connected_cli_input_unavailable') from None


def _out(directory: str, name: str, value: dict,
         forbidden_paths: tuple[str, ...]) -> dict:
    target = Path(directory)
    if (not target.is_absolute()
            or any(cap._path_is_within(target, Path(path))
                   for path in forbidden_paths)):
        raise InputError('windows_connected_cli_output_overlap')
    owned = create_private_directory(target)
    sha = write_private_json_exclusive(owned, name, value)
    return {'status': 'written', 'artifact': str(target / name),
            'artifact_sha256': sha,
            'binding_sha256': value.get('binding_sha256'),
            'plan_sha256': value.get('plan_sha256')}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='jev-integration-evaluator windows-connected')
    actions = parser.add_subparsers(dest='action', required=True)
    bind = actions.add_parser('bind', help='Recompute native package, wheel and installed origins')
    for name in ('package-plan', 'package-receipt', 'install-plan', 'install-receipt',
                 'trusted-package-receipt-sha256', 'trusted-install-receipt-sha256',
                 'output-dir'):
        bind.add_argument('--' + name, required=True)
    plan = actions.add_parser('plan', help='Bind exact public key and external observation schedule')
    for name in ('install-plan', 'binding', 'trusted-package-receipt-sha256',
                 'trusted-install-receipt-sha256', 'trusted-binding-sha256',
                 'reference-owner', 'observation-owner', 'launch-environment',
                 'observation', 'output-dir'):
        plan.add_argument('--' + name, required=True)
    configure = actions.add_parser('configure', help='Create one private connected Job session')
    for name in ('install-plan', 'binding', 'plan', 'session-dir'):
        configure.add_argument('--' + name, required=True)
    for action in ('launch', 'status', 'observe', 'stop'):
        command = actions.add_parser(action)
        for name in ('install-plan', 'binding', 'plan', 'session'):
            command.add_argument('--' + name, required=True)
        if action in ('launch', 'stop'):
            command.add_argument('--scope', required=True)
            command.add_argument('--approve-scope-sha256', required=True)
        if action in ('status', 'observe', 'stop'):
            command.add_argument('--approved-identity-sha256')
        if action == 'observe':
            command.add_argument('--role', choices=('ready', 'entrypoint_reached',
                                  'integration_reachable', 'outcome_verified'), required=True)
    return parser


def _execute(args) -> dict:
    if args.action == 'bind':
        package_plan = _json(args.package_plan)
        install_plan = _json(args.install_plan)
        binding = derive_windows_installed_binding(
            package_plan, _json(args.package_receipt), install_plan,
            _json(args.install_receipt),
            trusted_package_receipt_sha256=args.trusted_package_receipt_sha256,
            trusted_install_receipt_sha256=args.trusted_install_receipt_sha256)
        request = package_plan['request']
        return _out(args.output_dir, 'binding.json', binding,
                    tuple(request[name] for name in (
                        'host_root', 'wheelhouse', 'output_parent',
                        'environment_parent', 'implementation_bundle',
                        'template_directory')))
    if args.action == 'plan':
        install_plan = _json(args.install_plan)
        plan = plan_windows_connected_delivery(
            install_plan,
            trusted_package_receipt_sha256=args.trusted_package_receipt_sha256,
            trusted_install_receipt_sha256=args.trusted_install_receipt_sha256,
            installed_binding=_json(args.binding),
            trusted_binding_sha256=args.trusted_binding_sha256,
            reference_owner=_json(args.reference_owner),
            observation_owner=_json(args.observation_owner),
            launch_environment=_json(args.launch_environment),
            observation=_json(args.observation))
        request = install_plan['package_plan']['request']
        return _out(args.output_dir, 'plan.json', plan,
                    tuple(request[name] for name in (
                        'host_root', 'wheelhouse', 'output_parent',
                        'environment_parent', 'implementation_bundle',
                        'template_directory')) +
                    (plan['reference_owner']['path'],
                     plan['observation_owner']['path']))
    install_plan, binding, plan = (_json(args.install_plan), _json(args.binding),
                                    _json(args.plan))
    if args.action == 'configure':
        session = create_windows_connected_session(args.session_dir, plan,
                                                   install_plan, binding)
        return {'status': 'created', 'session_sha256': session['session_sha256'],
                'run_id': session['run_id']}
    session = _json(args.session)
    if args.action == 'launch':
        identity = launch_windows_connected_session(session, plan, install_plan,
            binding, scope=_json(args.scope),
            approved_scope_sha256=args.approve_scope_sha256)
        return {'status': 'launched', 'identity_sha256': identity['identity_sha256'],
                'run_id': session['run_id']}
    if args.action == 'status':
        return windows_connected_session_status(session, plan, install_plan, binding,
            trusted_identity_sha256=args.approved_identity_sha256)
    if args.action == 'observe':
        if not args.approved_identity_sha256:
            raise InputError('windows_connected_exact_observation_identity_required')
        result = observe_windows_connected_session(session, plan, install_plan,
            binding, approved_identity_sha256=args.approved_identity_sha256,
            role=args.role)
        return {'status': result['status'], 'role': result['role'],
                'observation_sha256': result['observation_sha256']}
    if not args.approved_identity_sha256:
        raise InputError('windows_connected_exact_stop_identity_required')
    return stop_windows_connected_session(session, plan, install_plan, binding,
        scope=_json(args.scope), approved_scope_sha256=args.approve_scope_sha256,
        approved_identity_sha256=args.approved_identity_sha256)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _execute(args)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (InputError, KeyError, ValueError, OSError, TypeError) as exc:
        code = str(exc)
        if re.fullmatch(r'[a-z][a-z0-9_]{0,119}', code) is None:
            code = 'windows_connected_cli_unavailable'
        print(json.dumps({'error': code}), file=sys.stderr)
        return 2

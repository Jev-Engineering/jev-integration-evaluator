"""Keep the registered-tool quickstart honest against the real parser and gate list (issue 57)."""
import argparse
import re
import shlex
from pathlib import Path

import pytest

from jev_integration_evaluator.cli import parser as cli_parser
from jev_integration_evaluator.recipe_lifecycle import recipe_lifecycle_row
from jev_integration_evaluator.registered_tool_qualification import (
    AUTHENTIC_GATES, GATES, PENDING, QUALIFIED, UNQUALIFIED, build_parser,
)

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = 'references/registered-tool-template-quickstart-v1.md'
CONSOLE = 'jev-integration-evaluator'
DRIVER = 'scripts/run_registered_tool_qualification.py'
JOURNEY = (
    'materialize', 'bind', 'package', 'package-build', 'install-plan', 'install',
    'delivery-plan', 'deploy', 'status', 'stop', 'disable', 'upgrade', 'rollback',
    'connected-installed-bind', 'connected-plan', 'connected-configure', 'connected-launch',
    'connected-status', 'connected-stop', 'connected-generation-plan',
    'connected-generation-transfer', 'connected-generation-status',
    'connected-generation-reconcile')
SOURCE_JOURNEY = ('implement-plan', 'implement-verify', 'implement-apply')


def _text() -> str:
    return (ROOT / DOCUMENT).read_text(encoding='utf-8')


def _choices(parser: argparse.ArgumentParser) -> dict:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    raise AssertionError('parser has no subcommands')


def _flags(parser: argparse.ArgumentParser) -> set[str]:
    return {option for action in parser._actions for option in action.option_strings}


TOP = _choices(cli_parser())
TEMPLATE = _choices(TOP['template'])


def _commands() -> list[list[str]]:
    """Every command line inside a fenced bash block, with continuations joined."""
    commands = []
    for block in re.findall(r'```bash\n(.*?)```', _text(), flags=re.S):
        for line in block.replace('\\\n', ' ').splitlines():
            if line.strip() and not line.lstrip().startswith('#'):
                commands.append(shlex.split(line))
    return commands


def _subparser(tokens: list[str]) -> tuple[str, argparse.ArgumentParser]:
    if tokens[0] == 'template':
        assert tokens[1] in TEMPLATE, tokens[1]
        return 'template ' + tokens[1], TEMPLATE[tokens[1]]
    assert tokens[0] in TOP, tokens[0]
    return tokens[0], TOP[tokens[0]]


def test_document_commands_parse_with_the_real_cli(capsys):
    commands = _commands()
    console = [tokens[1:] for tokens in commands if tokens[0] == CONSOLE]
    assert len(console) >= 30
    seen = set()
    for tokens in console:
        name, sub = _subparser(tokens)
        seen.add(name)
        shown = {token for token in tokens if token.startswith('--')}
        assert shown <= _flags(sub), (name, sorted(shown - _flags(sub)))
        try:
            # Placeholder values are enough: this checks required flags and choices only.
            parsed = cli_parser().parse_args(tokens)
        except SystemExit:
            pytest.fail('documented command is not accepted by the parser: ' + name)
        assert parsed.command == tokens[0]
    capsys.readouterr()
    assert {'template ' + name for name in JOURNEY} <= seen
    assert set(SOURCE_JOURNEY) <= seen
    assert {tokens[1] for tokens in commands if tokens[0] == CONSOLE} <= {'template', *TOP}


def test_every_named_subcommand_and_flag_exists():
    text = _text()
    named = set(re.findall(r'`template ([a-z][a-z-]*)', text))
    assert set(JOURNEY) <= named
    assert named <= set(TEMPLATE), sorted(named - set(TEMPLATE))
    for span in re.findall(r'`((?:template |implement-)[^`]*)`', text.replace('\n', ' ')):
        tokens = span.split()
        name, sub = _subparser(tokens)
        shown = {token for token in tokens if token.startswith('--')}
        assert shown <= _flags(sub), (name, sorted(shown - _flags(sub)))
    # Not evaluator flags: pytest's report flag, pip's installer flags and two flag-family prefixes.
    known = _flags(build_parser()) | {'--junitxml', '--require-hashes', '--no-index',
                                      '--approve-', '--trusted-'}
    for sub in (*TEMPLATE.values(), *(TOP[name] for name in TOP if name.startswith('implement-'))):
        known |= _flags(sub)
    shown = set(re.findall(r'(?<![\w-])--[a-z][a-z0-9-]*', text))
    assert shown <= known, sorted(shown - known)


def test_driver_commands_use_only_real_driver_flags(capsys):
    driver = [tokens for tokens in _commands() if DRIVER in tokens]
    assert driver and (ROOT / DRIVER).is_file()
    for tokens in driver:
        arguments = tokens[tokens.index(DRIVER) + 1:]
        assert {token for token in arguments if token.startswith('--')} <= _flags(build_parser())
        build_parser().parse_args(arguments)
    assert any('--require-offline-complete' in tokens for tokens in driver)
    capsys.readouterr()


def _matrix_rows() -> list[list[str]]:
    section = _text().split('\n## Support matrix\n', 1)[1].split('\n### ', 1)[0]
    rows = [[cell.strip() for cell in line.strip().strip('|').split('|')]
            for line in section.splitlines() if line.startswith('| `')]
    assert all(len(row) == 4 for row in rows)
    return rows


def test_support_matrix_is_the_packaged_gate_list():
    rows = _matrix_rows()
    assert [row[0].strip('`') for row in rows] == [gate['id'] for gate in GATES]
    for row, gate in zip(rows, GATES):
        assert row[1] == gate['title']
        assert row[2] == '`' + gate['documented_status'] + '`'
        cited = tuple(re.findall(r'`(tests/[^`]+)`', row[3]))
        assert cited == gate['required_modules']
        for module in cited:
            assert (ROOT / module).is_file(), module
    assert {gate['documented_status'] for gate in GATES} == {QUALIFIED, UNQUALIFIED, PENDING}


def test_authentic_gates_are_pending_and_never_qualified():
    rows = {row[0].strip('`'): row for row in _matrix_rows()}
    assert AUTHENTIC_GATES == ('provider_operation', 'authorized_canary', 'authorized_active',
                               'measured_benefit')
    for gate_id in AUTHENTIC_GATES:
        row = rows[gate_id]
        assert row[2] == '`pending`'
        assert row[3].startswith('none; needs ')
        assert 'qualified' not in ' '.join(row[1:]).lower()
        assert 'tests/' not in row[3]
    for gate in GATES:
        authentic = gate['id'] in AUTHENTIC_GATES
        assert (gate['kind'] == 'authentic') == authentic
        assert (gate['documented_status'] == PENDING) == authentic
        assert bool(gate['required_modules']) != authentic
    lowered = _text().lower()
    for phrase in ('provider operation', 'canary', 'active', 'measured benefit'):
        assert phrase in lowered
    assert '## What this does not establish' in _text()
    for claim in ('qualified live', 'live qualified', 'provider qualified', 'activated'):
        assert claim not in lowered


def test_gate_list_agrees_with_the_recipe_lifecycle_row():
    stages = recipe_lifecycle_row('python.C')['stages']
    gates = {gate['id']: gate for gate in GATES}
    for stage in ('canary_active', 'provider_operation', 'measured_benefit'):
        assert stages[stage]['status'] == PENDING
    assert stages['connected_upgrade']['status'] == \
        gates['connected_generation_transfer']['documented_status'] == UNQUALIFIED
    assert stages['connected_shadow']['status'] == \
        gates['connected_shadow_local_protocol']['documented_status'] == QUALIFIED
    for stage, gate_id in (('template_materialize', 'template_materialize'),
                           ('entrypoint_bind', 'entrypoint_bind'),
                           ('package_install', 'package_install'),
                           ('connected_shadow', 'connected_shadow_local_protocol'),
                           ('connected_upgrade', 'connected_generation_transfer')):
        assert set(stages[stage]['evidence']) <= set(gates[gate_id]['required_modules'])


def test_document_is_linked_and_carries_no_sensitive_material():
    text = _text()
    name = Path(DOCUMENT).name
    for linking in ('README.md', 'SKILL.md', 'ONBOARDING.md'):
        assert name in (ROOT / linking).read_text(encoding='utf-8'), linking
    assert DRIVER in (ROOT / 'CONTRIBUTING.md').read_text(encoding='utf-8')
    assert b'\r' not in (ROOT / DOCUMENT).read_bytes()
    assert 'PRIVATE KEY' not in text and 'Bearer ' not in text
    assert not re.search(r'[a-z]+://[^\s/]*@', text)
    assert not re.search(r'[A-Za-z]:\\|/home/|/Users/', text)
    for target in re.findall(r'\]\((?!#)([^)#]+)(?:#[^)]*)?\)', text):
        assert (ROOT / 'references' / target).resolve().exists(), target

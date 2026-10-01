"""Each use-case operator reference has a checked quickstart, parameter table and refusal list.

The quickstart commands are parsed with the real argument parser, the launch
environment names are compared with the finite connected profiles, and every
quoted refusal must exist in code or in that template's own tests (issue 59).
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import shlex

import pytest

from jev_integration_evaluator import template_connected_delivery
from jev_integration_evaluator.cli import parser


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = {'graph': ('L', 'graph-l-v1', 'graph-host'),
             'retrieval': ('D', 'retrieval-d-v1', 'retrieval-host'),
             'completion': ('E', 'completion-e-v1', 'completion-host'),
             'claim': ('M', 'claim-m-v1', 'claim-host'),
             'retention': ('H', 'retention-h-v1', 'retention-host')}
SECTIONS = ('Quickstart', 'Parameters and bindings', 'Unsupported cases')
# Lifecycle stages the issue requires each template to document, in order.
ORDERED = ('template validate', 'template bind', 'template materialize', 'implement-plan',
           'implement-apply', 'template package', 'template package-build',
           'template install-plan', 'template install', 'template delivery-plan',
           'template deploy', 'template observe', 'template status', 'template disable',
           'template upgrade', 'template rollback', 'implement-rollback',
           'template connected-installed-bind', 'template connected-plan',
           'template connected-configure', 'template connected-launch',
           'template connected-status', 'template connected-stop')
ENV_NAME = re.compile(r'^[A-Z][A-Z0-9_]{2,}$')


def _document(name: str) -> str:
    raw = (ROOT / 'references' / f'{name}-template-offline-v1.md').read_bytes()
    assert b'\r' not in raw
    return raw.decode('utf-8')


def _sections(name: str) -> dict[str, str]:
    parts = re.split(r'^## (.+)$', _document(name), flags=re.MULTILINE)
    return {title.strip(): body for title, body in zip(parts[1::2], parts[2::2])}


def _subparsers(target: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in target._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _flags(target: argparse.ArgumentParser) -> set[str]:
    return {option for action in target._actions for option in action.option_strings}


def _commands(body: str) -> list[list[str]]:
    lines = []
    for block in re.findall(r'```bash\n(.*?)```', body, flags=re.DOTALL):
        for line in block.splitlines():
            if line.startswith('jev-integration-evaluator '):
                assert not line.endswith('\\'), 'one command per line keeps this check exact'
                lines.append(shlex.split(line)[1:])
            else:
                assert not line.strip() or line.lstrip().startswith('#'), line
    return lines


def _spans(body: str) -> list[str]:
    prose = re.sub(r'```.*?```', '', body, flags=re.DOTALL)
    return re.findall(r'`([^`\n]+)`', prose)


def _table_rows(body: str) -> list[list[str]]:
    rows = [line for line in body.splitlines() if line.startswith('|')]
    assert rows[0] == '| Name | Where | Allowed values | Default | What refuses |'
    assert set(rows[1].replace('|', '').split()) == {'---'}
    parsed = [[cell.strip() for cell in row.strip('|').split('|')] for row in rows[2:]]
    assert parsed and all(len(row) == 5 and all(row) for row in parsed)
    return parsed


def _corpus(name: str) -> str:
    files = [*sorted((ROOT / 'jev_integration_evaluator').rglob('*.py')),
             *sorted((ROOT / 'examples').rglob('*.py')),
             *sorted((ROOT / 'tests').glob(f'test_use_case_{name}_*.py'))]
    assert len(files) > 20
    return '\n'.join(path.read_text(encoding='utf-8') for path in files)


@pytest.mark.parametrize('name', sorted(TEMPLATES))
def test_reference_has_the_three_operator_sections_in_order(name):
    text = _document(name)
    sections = _sections(name)
    positions = [text.index(f'\n## {title}\n') for title in SECTIONS]
    assert positions == sorted(positions)
    for title in SECTIONS:
        assert text.count(f'\n## {title}\n') == 1
        assert len(sections[title].strip()) > 400, (name, title)
    assert len(re.findall(r'^- ', sections['Unsupported cases'], flags=re.MULTILINE)) >= 8
    assert len(_table_rows(sections['Parameters and bindings'])) >= 12


@pytest.mark.parametrize('name', sorted(TEMPLATES))
def test_quickstart_commands_parse_with_the_real_parser_in_lifecycle_order(name):
    _, profile, script = TEMPLATES[name]
    body = _sections(name)['Quickstart']
    commands = _commands(body)
    cli = parser()
    seen = []
    for arguments in commands:
        try:
            parsed = cli.parse_args(arguments)
        except SystemExit:
            raise AssertionError(f'documented command is not accepted: {arguments}') from None
        label = parsed.command
        if parsed.command == 'template':
            label = 'template ' + parsed.template_action
            if parsed.template_action == 'connected-plan':
                assert parsed.host_profile == profile
        seen.append(label)
    # Every required stage is present, and first occurrences follow the lifecycle.
    first = [seen.index(stage) for stage in ORDERED]
    assert first == sorted(first), (name, seen)
    phases = [parsed for parsed in map(cli.parse_args, commands)
              if parsed.command == 'implement-verify']
    assert [parsed.phase for parsed in phases] == ['baseline', 'modified']
    assert f'`{script}`' in body and f'`{profile}`' in body
    # The deploy command is documented in both of its exclusive forms.
    deploys = [parsed for parsed in map(cli.parse_args, commands)
               if parsed.command == 'template' and parsed.template_action == 'deploy']
    assert [bool(parsed.plan) for parsed in deploys] == [True, False]
    assert deploys[1].scope and deploys[1].approve_scope_sha256


@pytest.mark.parametrize('name', sorted(TEMPLATES))
def test_every_named_subcommand_and_flag_exists(name):
    cli = parser()
    top = _subparsers(cli)
    template = _subparsers(top['template'])
    every_flag = _flags(cli) | {flag for sub in (*top.values(), *template.values())
                                for flag in _flags(sub)}
    sections = _sections(name)
    for title in SECTIONS:
        body = sections[title]
        for span in _spans(body):
            words = span.split()
            if words[0] == 'template':
                assert len(words) >= 2 and words[1] in template, (name, span)
            if words[0].startswith('implement-'):
                assert words[0] in top, (name, span)
            for word in words:
                if word.startswith('--') and not word.endswith('...'):
                    assert word in every_flag, (name, span)
        for arguments in _commands(body):
            target = top[arguments[0]]
            if arguments[0] == 'template':
                target = template[arguments[1]]
            for word in arguments:
                if word.startswith('--'):
                    assert word in _flags(target), (name, arguments[:2], word)
    # The two abbreviated flag families in the prose are real prefixes.
    assert any(flag.startswith('--approve') for flag in every_flag)
    assert any(flag.startswith('--trusted') for flag in every_flag)


@pytest.mark.parametrize('name', sorted(TEMPLATES))
def test_launch_environment_names_match_the_finite_profile_or_the_template_tests(name):
    letter, profile_name, script = TEMPLATES[name]
    profile = template_connected_delivery._PROFILES[profile_name]
    accepted = set(profile['references']) | set(profile['allowed']) | {'SSL_CERT_FILE'}
    tests = '\n'.join(path.read_text(encoding='utf-8')
                      for path in sorted((ROOT / 'tests').glob(f'test_use_case_{name}_*.py')))
    body = _sections(name)['Parameters and bindings']
    documented = {}
    for row in _table_rows(body):
        for span in re.findall(r'`([^`]+)`', row[0]):
            if ENV_NAME.match(span):
                assert span not in documented, (name, span)
                documented[span] = row
    for variable, row in documented.items():
        assert variable in accepted or variable in tests, (name, variable)
        # A row may call a name a connected launch input only if the profile accepts it.
        assert ('connected launch environment' in row[1]) == (variable in accepted), (name, variable)
        assert variable not in profile['injected']
    # Completeness: nothing the profile accepts is left undocumented.
    assert accepted <= set(documented), (name, sorted(accepted - set(documented)))
    for reference in profile['references']:
        assert 'required' in documented[reference][3]
    for binary in profile['binary']:
        assert '`0`, `1`' in documented[binary][2], (name, binary)
    for injected in profile['injected']:
        assert f'`{injected}`' in body
    assert f'`{script}`' in body and f'`{profile_name}`' in body
    assert profile_name.split('-')[1] == letter.lower()


@pytest.mark.parametrize('name', sorted(TEMPLATES))
def test_quoted_refusals_exist_in_code_or_in_the_template_tests(name):
    corpus = _corpus(name)
    sections = _sections(name)
    checked = 0
    for span in _spans(sections['Unsupported cases']):
        if span.split()[0] == 'template':
            continue
        assert span in corpus, (name, span)
        checked += 1
    assert checked >= 8
    # Refusal diagnostics in the table are literal too.
    for row in _table_rows(sections['Parameters and bindings']):
        for span in re.findall(r'`([^`]+)`', row[4]):
            if span.split()[0] == 'template' or ENV_NAME.match(span) or span in ('0', '1'):
                continue
            assert span in corpus, (name, row[0], span)


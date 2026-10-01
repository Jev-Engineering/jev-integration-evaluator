"""Fail when a required test module was skipped, missing or failing in a JUnit report.

A passing pytest exit code does not show that an environment-gated installed
journey actually executed. This check reads the JUnit report and requires
every named module to have at least one test case, with no skipped, failed
or errored case. It executes nothing and reads only the given report.
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET


def check(report: str, modules: list[str]) -> list[str]:
    """Return one problem line per required module that is not fully executed."""
    root = ET.parse(report).getroot()
    counts = {module: {'cases': 0, 'skipped': 0, 'failed': 0} for module in modules}
    for case in root.iter('testcase'):
        row = counts.get(case.get('classname') or '')
        if row is None:
            continue
        row['cases'] += 1
        if case.find('skipped') is not None:
            row['skipped'] += 1
        if case.find('failure') is not None or case.find('error') is not None:
            row['failed'] += 1
    problems = []
    for module in modules:
        row = counts[module]
        if not row['cases']:
            problems.append(f'{module}: no test case collected')
        elif row['skipped'] or row['failed']:
            problems.append(f"{module}: {row['cases']} cases, {row['skipped']} skipped, "
                            f"{row['failed']} failed")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--junit', required=True, help='JUnit XML report written by pytest')
    parser.add_argument('--modules-file', required=True,
                        help='Text file with one required test module per line')
    args = parser.parse_args(argv)
    with open(args.modules_file, encoding='utf-8') as stream:
        modules = [line.strip() for line in stream
                   if line.strip() and not line.lstrip().startswith('#')]
    if not modules or len(set(modules)) != len(modules):
        print('required module list is empty or contains duplicates', file=sys.stderr)
        return 2
    problems = check(args.junit, modules)
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f'required modules: {len(modules)}; incomplete: {len(problems)}')
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())

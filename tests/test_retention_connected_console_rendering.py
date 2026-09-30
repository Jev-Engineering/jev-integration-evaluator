"""Check authored audit syntax and JSONL framing without importing a host."""
import ast
from pathlib import Path


def test_connected_retention_audit_renders_valid_jsonl():
    helper = ast.parse(Path(__file__).with_name('test_use_case_retention_bind.py').read_text())
    audit = next(ast.literal_eval(node.value) for node in ast.walk(helper)
                 if isinstance(node, ast.Assign) and any(
                     isinstance(target, ast.Name) and target.id == 'new_audit'
                     for target in node.targets))
    tree = ast.parse('class Audit:\n' + audit)
    raw = next(node.value for node in ast.walk(tree)
               if isinstance(node, ast.Assign) and any(
                   isinstance(target, ast.Name) and target.id == 'raw' for target in node.targets))
    assert isinstance(raw, ast.Call) and isinstance(raw.func.value, ast.BinOp)
    assert ast.literal_eval(raw.func.value.right) == '\n'

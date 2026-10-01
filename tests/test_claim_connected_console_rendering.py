"""Check authored console syntax and JSONL framing without importing a host."""
import ast
from pathlib import Path


def test_connected_claim_console_renders_valid_jsonl_audit():
    helper = ast.parse(Path(__file__).with_name('test_use_case_claim_bind.py').read_text())
    function = next(node for node in helper.body
                    if isinstance(node, ast.FunctionDef) and node.name == '_connected_console')
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<authored-console>', 'exec'),
         namespace)
    console = namespace['_connected_console']('assess_claim', 'host_claim_support')
    tree = ast.parse(console)
    raw = next(node.value for node in ast.walk(tree)
               if isinstance(node, ast.Assign) and any(
                   isinstance(target, ast.Name) and target.id == 'raw' for target in node.targets))
    assert isinstance(raw, ast.Call) and isinstance(raw.func.value, ast.BinOp)
    assert ast.literal_eval(raw.func.value.right) == '\n'

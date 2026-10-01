"""Source-faithful contracts and precise partial installed status for issue 59."""
import ast
import contextlib
import copy
import importlib.metadata
import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

from jev_integration_evaluator import use_case_templates
from jev_integration_evaluator.integrations.errors import UnsupportedShape
from jev_integration_evaluator.integrations.lifecycle import plan_implementation
from jev_integration_evaluator.io import InputError, read_json
from jev_integration_evaluator.template_catalog import (
    bind_template, materialize_template, prepare_template_binding, validate_template_request,
)
from jev_integration_evaluator.use_case_templates import (
    EVIDENCE_CELLS, NEVER_OFFLINE_QUALIFIED, inspect_use_case_source, use_case_matrix,
)


ROOT = Path(__file__).resolve().parents[1]


def fixture_module(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve the module namespace during class creation.
    import sys
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_six_rows_are_source_bound_and_limit_installed_claims_to_l_d_e_m_and_h():
    matrix = use_case_matrix()
    assert [row["id"] for row in matrix["rows"]] == ["C", "L", "D", "E", "M", "H"]
    for row in matrix["rows"]:
        receipt = inspect_use_case_source(ROOT, row["id"])
        assert receipt["source_sha256"] == row["source_sha256"]
        assert not receipt["target_imported"] and not receipt["installed_verified"]
        assert row["mode"] == "off" and row["benefit"] == "unknown"
        if row["id"] in ("L", "D", "E", "M", "H"):
            assert receipt["consumer_adapter_sha256"] == row["consumer_adapter_sha256"]
            if row["id"] == "D":
                assert receipt["consumer_corpus_sha256"] == row["consumer_corpus_sha256"]
            if row["id"] == "E":
                assert row["connected_shadow"] == "qualified_offline_e_installed_shadow_protocol"
                assert row["connected_upgrade"] == "pending"
            state = f"qualified_offline_{row['id'].lower()}_synthetic_host"
            assert {row[k] for k in ("apply", "install", "launch")} == {state}
            assert {row[k] for k in ("materialize", "verify", "status", "disable",
                                     "upgrade", "rollback")} == {state}
            assert row["bind"] == (state if row["id"] in ("D", "E", "H", "L", "M") else
                                   f"pending_{row['id'].lower()}_console_binding")
            assert row["provider"] == "pending"
        else:
            assert {row[k] for k in ("apply", "install", "launch", "provider")} == {"pending"}
            assert {row[k] for k in ("materialize", "bind", "verify", "status",
                                     "disable", "upgrade", "rollback")} == {"pending"}
        assert row["recipe"] == f'python.{row["id"]}@1.0'
        assert row["contract_id"] == f'use-case.{row["id"]}@1.0.0'


def _defined_symbols(path: Path) -> set[str]:
    """Top-level functions and Class.method names, read without importing the fixture."""
    names = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.update(node.name + "." + item.name for item in node.body
                         if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)))
    return names


def test_host_interfaces_name_real_functions_in_the_pinned_source_contract():
    for row in use_case_matrix()["rows"]:
        pinned = {row["source"]} | ({row["consumer_adapter"]} if row["id"] != "C" else set())
        files = {interface["file"] for interface in row["host_interfaces"]}
        # Every pinned file contributes at least one bound host function.
        assert files == pinned, row["id"]
        for interface in row["host_interfaces"]:
            assert interface["symbol"] in _defined_symbols(ROOT / interface["file"]), (
                row["id"], interface)
        if row["id"] != "C":
            assert {"file": row["consumer_adapter"],
                    "symbol": "merge" if row["id"] == "L" else "commit"} in row["host_interfaces"]


def test_every_lifecycle_cell_is_explicit_and_every_qualified_cell_has_existing_evidence():
    required = [line.strip() for line in
                (ROOT / ".github/required-installed-journeys.txt").read_text().splitlines()
                if line.strip() and not line.startswith("#")]
    rows = {row["id"]: row for row in use_case_matrix()["rows"]}
    for letter, row in rows.items():
        assert tuple(row["evidence"]) == EVIDENCE_CELLS
        state = "pending" if letter == "C" else f"qualified_offline_{letter.lower()}_synthetic_host"
        assert row["configure"] == row["normal_start"] == state
        for cell in EVIDENCE_CELLS:
            paths = row["evidence"][cell]
            qualified = str(row.get(cell, "pending")).startswith("qualified_offline_")
            assert qualified == bool(paths), (letter, cell)
            assert len(paths) == len(set(paths))
            for path in paths:
                assert path.startswith("tests/test_use_case_") and path.endswith(".py")
                assert (ROOT / path).is_file(), (letter, cell, path)
                source = (ROOT / path).read_text(encoding="utf-8")
                # A cited module must itself drive the stage it is cited for.
                if cell == "configure":
                    assert "reviewed_configuration_sha256" in source, (letter, path)
                if cell in ("normal_start", "launch"):
                    assert "launch_session(" in source, (letter, path)
                if cell == "connected_shadow":
                    assert "launch_connected_session(" in source, (letter, path)
                    # The hosted Linux 3.13 leg fails if this module skips.
                    assert path[:-3].replace("/", ".") in required, (letter, path)
        for cell in NEVER_OFFLINE_QUALIFIED:
            assert row["evidence"][cell] == []
        # No row borrows another use case's installed evidence.
        for other, other_row in rows.items():
            if other != letter:
                assert not ({path for paths in row["evidence"].values() for path in paths}
                            & {path for paths in other_row["evidence"].values() for path in paths})
    assert all(rows["C"]["evidence"][cell] == [] for cell in EVIDENCE_CELLS)
    for letter in ("L", "D", "E"):
        assert rows[letter]["connected_shadow"] == (
            f"qualified_offline_{letter.lower()}_installed_shadow_protocol")

    for letter in ("M", "H"):
        assert rows[letter]["connected_shadow"] == (
            f"qualified_offline_{letter.lower()}_installed_shadow_protocol")
    for letter in ("L", "D", "E", "M", "H"):
        assert rows[letter]["connected_upgrade"] == "pending"


@pytest.mark.parametrize("mutation", ["unevidenced", "overclaimed", "pending_with_evidence",
                                      "missing_cell", "foreign_interface"])
def test_loader_and_schema_reject_evidence_and_interface_mismatches(monkeypatch, mutation):
    matrix = use_case_matrix()
    row = matrix["rows"][2]
    assert row["id"] == "D"
    if mutation == "unevidenced":
        row["evidence"]["install"] = []
    elif mutation == "overclaimed":
        row["provider"] = "qualified_offline_d_synthetic_host"
        row["evidence"]["provider"] = ["tests/test_use_case_retrieval_connected.py"]
    elif mutation == "pending_with_evidence":
        row["evidence"]["connected_upgrade"] = ["tests/test_use_case_retrieval_connected.py"]
    elif mutation == "missing_cell":
        del row["evidence"]["configure"]
    else:
        row["host_interfaces"].append({"file": "examples/coding-agent/agent.py",
                                       "symbol": "dispatch_once"})
    schema = read_json(ROOT / "schemas/use-case-template-matrix-v1.schema.json")
    valid = jsonschema.Draft202012Validator(schema).is_valid(matrix)
    assert valid == (mutation in ("unevidenced", "pending_with_evidence", "foreign_interface"))
    monkeypatch.setattr(use_case_templates, "read_json", lambda path: matrix)
    with pytest.raises(InputError):
        use_case_matrix()


def test_matrix_schema_copies_are_identical_and_reference_names_new_cells():
    root = ROOT / "schemas/use-case-template-matrix-v1.schema.json"
    packaged = ROOT / "jev_integration_evaluator/data/use-case-template-matrix-v1.schema.json"
    assert root.read_bytes() == packaged.read_bytes()
    text = (ROOT / "references/use-case-template-matrix-v1.md").read_text(encoding="utf-8")
    for name in ("host_interfaces", "configure", "normal_start", "evidence"):
        assert "`" + name + "`" in text
    for row in use_case_matrix()["rows"]:
        for interface in row["host_interfaces"]:
            assert "`" + interface["symbol"] + "`" in text, (row["id"], interface)
        for paths in row["evidence"].values():
            for path in paths:
                assert path in text, (row["id"], path)


USE_CASES = ("L", "D", "E", "M", "H")


def _use_case_row(letter):
    row = next(row for row in use_case_matrix()["rows"] if row["id"] == letter)
    assert row["id"] == letter
    return row


@pytest.mark.parametrize("letter", USE_CASES)
def test_source_drift_fails_closed(tmp_path, letter):
    row = _use_case_row(letter)
    if letter == "L":
        assert row == use_case_matrix()["rows"][1]
    source = tmp_path / row["source"]
    source.parent.mkdir(parents=True)
    source.write_bytes((ROOT / row["source"]).read_bytes() + b"\n# drift\n")
    with pytest.raises(InputError, match="changed"):
        inspect_use_case_source(tmp_path, letter)


@pytest.mark.parametrize("letter", USE_CASES)
def test_consumer_adapter_and_corpus_drift_fail_closed(tmp_path, letter):
    row = _use_case_row(letter)
    assert row["connected_shadow"] == (
        f"qualified_offline_{letter.lower()}_installed_shadow_protocol")
    assert row["connected_upgrade"] == "pending"
    assert row["provider"] == "pending" and row["benefit"] == "unknown"
    pinned = [key for key in ("source", "consumer_adapter", "consumer_corpus") if key in row]
    assert pinned == ["source", "consumer_adapter"] + (["consumer_corpus"] if letter == "D" else [])
    for key in pinned:
        path = tmp_path / row[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / row[key]).read_bytes())
    # The untouched copy matches, so each refusal below is caused by its drift.
    assert inspect_use_case_source(tmp_path, letter)["status"] == "source_matched"
    adapter = tmp_path / row["consumer_adapter"]
    adapter.write_bytes(adapter.read_bytes() + b"\n# drift\n")
    with pytest.raises(InputError, match="adapter changed"):
        inspect_use_case_source(tmp_path, letter)
    if letter == "D":
        adapter.write_bytes((ROOT / row["consumer_adapter"]).read_bytes())
        corpus = tmp_path / row["consumer_corpus"]
        corpus.write_bytes(corpus.read_bytes() + b" ")
        with pytest.raises(InputError, match="corpus changed"):
            inspect_use_case_source(tmp_path, "D")


def _registered_tool_is_single_host_checked_dispatch():
    agent = fixture_module("examples/coding-agent/agent.py", "issue59_tools")
    class Choice:
        def __init__(self, value): self.value = value
        def choose(self, *_): return self.value
    class Executor:
        calls = 0
        def execute_tool(self, *_):
            self.calls += 1
            return type("Result", (), {"exit_code": 0})()
    executor = Executor()
    assert not agent.dispatch_once(Choice("write_file"), executor, "task", agent.REGISTERED_CAPABILITIES,
                                   arguments={"path": "x", "content": "y"}, granted_permissions=("read",))
    assert not agent.dispatch_once(Choice("unknown"), executor, "task", agent.REGISTERED_CAPABILITIES,
                                   arguments={}, granted_permissions=("read",))
    assert executor.calls == 0
    assert agent.dispatch_once(Choice("read_file"), executor, "task", agent.REGISTERED_CAPABILITIES,
                               arguments={"path": "x"}, granted_permissions=("read",))
    assert executor.calls == 1


def _graph_revision_and_approval_are_host_owned():
    graph = fixture_module("examples/graph-system/entities.py", "issue59_graph")
    left = graph.Entity("a", "One", "US", "x", "source-a")
    right = graph.Entity("b", "One", "US", "x", "source-b")
    store = graph.InMemoryGraph(left, right, revision=4)
    class Same:
        def classify(self, *_): return "same"
    assert graph.reconcile(Same(), store, left, right, False, 4) is None
    assert graph.reconcile(Same(), store, left, right, True, 3) is None
    assert graph.reconcile(Same(), store, left, right, True, 4, audit=lambda _: (_ for _ in ()).throw(ValueError())) is None
    assert store.revision == 4 and store.merges == []
    receipt = graph.reconcile(Same(), store, left, right, True, 4)
    assert receipt["sources"] == ["source-a", "source-b"] and store.revision == 5
    assert graph.reconcile(Same(), store, left, right, True, 4) is None


def _retrieval_missing_and_material_contradiction():
    rag = fixture_module("examples/rag-system/pipeline.py", "issue59_rag_d")
    support = rag.Passage("p1", "s1", "0:12", "status approved", "claim", "supports")
    conflict = rag.Passage("p2", "s2", "0:10", "status denied", "claim", "contradicts")
    class Retriever:
        def __init__(self, passages): self.passages = passages
        def retrieve(self, _): return self.passages
    class Generator:
        calls = 0
        def generate(self, _, bundle):
            self.calls += 1
            return tuple(p.passage_id for p in bundle.passages)
    generator = Generator()
    empty = rag.answer_with_evidence(Retriever([]), generator, "status", policy="lexical")
    assert empty.answer is None and empty.evidence.status == "insufficient" and generator.calls == 0
    answer = rag.answer_with_evidence(Retriever([support, conflict]), generator, "approved", policy="lexical")
    assert answer.answer == ("p1", "p2") and generator.calls == 1
    assert answer.evidence.citation("p2").source_id == "s2"


def _completion_ignores_success_flag_without_raw_goal():
    oracle = fixture_module("examples/coding-agent/completion_oracle.py", "issue59_completion")
    case = json.loads((ROOT / "examples/coding-agent/completion/cases.json").read_text())["cases"][0]
    raw = case["initial_raw_state"]
    assert not oracle.exact_goal(raw, case["objective"])
    # An executor's success-shaped report is not an independent postcondition.
    assert not oracle.exact_goal(dict(raw, executor_success=True), case["objective"])
    goal = dict(raw, status="closed", labels=["verified"], revision=2)
    assert oracle.exact_goal(goal, case["objective"])
    assert not oracle.exact_goal(dict(goal, unrequested=["extra"]), case["objective"])
    labels = json.loads((ROOT / "examples/coding-agent/completion/scorer-labels.json").read_text())["labels"]
    empty_trace = oracle.score_trace(case, labels[0], [], raw, [])
    assert not empty_trace["verified_completion"] and empty_trace["safety_violations"] == 0


def _claim_consumer_rejects_fabrication_and_partial_critical_claim():
    rag = fixture_module("examples/rag-system/pipeline.py", "issue59_rag_m")
    passage = rag.Passage("p1", "s1", "0:5", "alpha supported", "c1", "supports")
    bundle = rag.EvidenceBundle("q", (passage,), (("p1", "relevant"),), "ready")
    good = rag.AtomicClaim("c1", "alpha", (rag.EvidenceRef("p1", 0, 5, "alpha"),))
    fake = rag.AtomicClaim("c2", "beta", (rag.EvidenceRef("missing", 0, 4, "beta"),))
    assert rag.review_claims(bundle, rag.DraftAnswer((fake,)), rag.ClaimRequest(frozenset({"c2"})), policy="deterministic").status == "blocked"
    result = rag.review_claims(bundle, rag.DraftAnswer((good, fake)), rag.ClaimRequest(frozenset({"c1"})), policy="deterministic")
    assert result.status == "revised" and result.final.claims == (good,)
    class Retriever:
        def retrieve(self, _): return [passage]
    class Generator:
        def generate(self, *_): return rag.DraftAnswer((good,))
    delivery = rag.answer_with_claim_review(Retriever(), Generator(), "q", rag.ClaimRequest(frozenset({"c1"})), policy="deterministic")
    assert delivery.outcome.status == "request_more_evidence" and delivery.outcome.reason == "audit_failed"


def _retention_preserves_pins_bytes_and_explicit_mode():
    oracle = fixture_module("examples/coding-agent/retention_oracle.py", "issue59_retention")
    case = json.loads((ROOT / "examples/coding-agent/retention/histories.json").read_text())["cases"][0]
    original = case["items"]
    pins = {pin["id"] for pin in case["pins"]}
    retained = [item for item in original if item["id"] in pins]
    safe = oracle.raw_postconditions(case, retained, True, "/prune", case["token_budget"])
    assert not any(safe[key] for key in ("pin_loss", "byte_or_provenance_loss", "over_budget_commit", "wrong_mode_mutation"))
    assert oracle.raw_postconditions(case, retained[1:], True, "/prune", case["token_budget"])["pin_loss"]
    damaged = [dict(item, text=item["text"] + " changed") for item in retained]
    assert oracle.raw_postconditions(case, damaged, True, "/prune", case["token_budget"])["byte_or_provenance_loss"]
    assert oracle.raw_postconditions(case, retained, True, "/compact", case["token_budget"])["wrong_mode_mutation"]
    question = json.loads((ROOT / "examples/coding-agent/retention/reader-questions.json").read_text())["questions"][0]
    label = json.loads((ROOT / "examples/coding-agent/retention/scorer-only.json").read_text())["labels"][0]
    assert oracle.score_recall(question["question"], label, retained, [])["success"]
    missing = oracle.score_recall(question["question"], label, retained, [], missing_reader=True)
    assert missing["missing"] and not missing["success"]


CONSUMER_CONTRACTS = {
    "C": _registered_tool_is_single_host_checked_dispatch,
    "L": _graph_revision_and_approval_are_host_owned,
    "D": _retrieval_missing_and_material_contradiction,
    "E": _completion_ignores_success_flag_without_raw_goal,
    "M": _claim_consumer_rejects_fabrication_and_partial_critical_claim,
    "H": _retention_preserves_pins_bytes_and_explicit_mode,
}


@pytest.mark.parametrize("letter", ("C",) + USE_CASES)
def test_use_case_consumer_keeps_host_authority(letter):
    assert set(CONSUMER_CONTRACTS) == {row["id"] for row in use_case_matrix()["rows"]}
    CONSUMER_CONTRACTS[letter]()


# Fail-closed planner refusals, decided before any installed host exists.
#
# "Policy" is the recipe policy object of the implementation specification
# (the schema fixes the required keys per recipe) and the four host-authored
# startup inputs a console binding must name. "Secret" is the reviewed runtime
# configuration: it may hold a credential *reference* (`env:NAME`) or null,
# never a value, and it must be present. Everything here is offline synthetic.
POLICY_KEYS = {
    "L": ("fallback", "mutating_actions", "nonmutating_actions"),
    "D": ("fallback", "max_items", "preserve_contradictions", "preserve_uncertain"),
    "E": ("fallback", "success_action", "failure_action", "postconditions"),
    "M": ("fallback", "failed_claims_action"),
    "H": ("fallback", "max_items", "choice_field"),
}
HOST_POLICY_INPUTS = ("budget_limits", "audit_log", "dependency_plan", "startup_options")
SPEC_ROOT_REFUSAL = "Invalid implementation specification at "
POLICY_REFUSAL = "Invalid implementation specification at policy"
POSTCONDITION_REFUSAL = "Post-action verification requires an independent state-change assertion"
BINDING_REFUSAL = "Invalid template-entrypoint-binding-v1 contract"
UNRESOLVED_INPUT_REFUSAL = "Missing or ambiguous entrypoint function: absent_host_policy"
CREDENTIAL_REFUSAL = "Runtime configuration must remain off with credential reference only"
CONFIGURATION_REFUSAL = ("Supported host lifecycle requires reviewed lock and configuration; "
                         "packages also require a bound entrypoint")


@contextlib.contextmanager
def _portable_fixture_authoring():
    """Author the reviewed host fixtures identically on every platform.

    The fixtures hash the text they write, so it must stay LF where the
    platform default is CRLF. They also pin the local build-tool versions in a
    pyproject that these planner-level tests never build; an absent tool gets a
    fixed label instead of making the refusal checks depend on it.
    """
    write_text = Path.write_text
    version = importlib.metadata.version

    def lf_write_text(self, data, encoding=None, errors=None, newline=None):
        return write_text(self, data, encoding=encoding, errors=errors,
                          newline="\n" if newline is None else newline)

    def pinned_version(name):
        try:
            return version(name)
        except importlib.metadata.PackageNotFoundError:
            if name not in ("pip", "setuptools", "wheel"):
                raise
            return "0+absent"

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "write_text", lf_write_text)
        patch.setattr(importlib.metadata, "version", pinned_version)
        yield


def _bound_request(letter, target):
    """A fresh source-bound console request per use case; no target code runs."""
    # Imported here: these modules import this one for `fixture_module`.
    with _portable_fixture_authoring():
        if letter == "L":
            from tests.test_use_case_graph_bind import BINDING as binding, _bound_host
            request = _bound_host(target)[-1]
        elif letter == "D":
            from tests.test_use_case_retrieval_bind import BINDING as binding, _bound_host
            request = _bound_host(target)[-1]
        elif letter == "E":
            from tests.test_use_case_completion_host import _binding, _source_host
            binding, request = _binding(), _source_host(target)[-1]
        elif letter == "M":
            from tests.test_use_case_claim_bind import BINDING as binding, _bound_host
            request = _bound_host(target)[-1]
        else:
            assert letter == "H"
            from tests.test_use_case_retention_bind import BINDING as binding, _bound_host
            request = _bound_host(target)[-1]
    bound = prepare_template_binding(target, request, binding)["request"]
    spec = bound["implementation_spec"]
    assert spec["recipe"]["id"] == "python." + letter
    assert spec["entrypoint_binding"]["kind"] == "task-loop-v1"
    assert validate_template_request(target, bound)["status"] == "validated"
    return request, copy.deepcopy(binding), bound


def _tree(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


def _refused(tmp_path, before, operation, error, reason):
    with pytest.raises(InputError) as caught:
        operation()
    assert type(caught.value) is error and str(caught.value) == reason
    # No generated file in the host and no owned directory beside it.
    assert _tree(tmp_path / "host") == before
    assert [path.name for path in tmp_path.iterdir()] == ["host"]


def _refused_by_every_planner(tmp_path, before, request, binding, bound, mutate, reason):
    """The same spec defect is refused by bind, validate, materialize and plan."""
    target = tmp_path / "host"
    unbound, mutated = copy.deepcopy(request), copy.deepcopy(bound)
    mutate(unbound["implementation_spec"])
    mutate(mutated["implementation_spec"])
    assert mutated != bound
    spec = mutated["implementation_spec"]
    for operation in (
            lambda: prepare_template_binding(target, unbound, binding),
            lambda: bind_template(target, unbound, binding, tmp_path / "bound"),
            lambda: validate_template_request(target, mutated),
            lambda: materialize_template(target, mutated, tmp_path / "template"),
            lambda: plan_implementation(target, mutated["reviewed_inventory"],
                                        spec["candidate_id"], spec, tmp_path / "bundle")):
        _refused(tmp_path, before, operation, InputError, reason)


@pytest.mark.parametrize("letter", USE_CASES)
def test_missing_recipe_policy_is_refused_before_any_write(tmp_path, letter):
    request, binding, bound = _bound_request(letter, tmp_path / "host")
    before = _tree(tmp_path / "host")
    assert set(bound["implementation_spec"]["policy"]) == set(POLICY_KEYS[letter])

    def absent(spec):
        del spec["policy"]

    def empty(spec):
        spec["policy"] = {}

    _refused_by_every_planner(tmp_path, before, request, binding, bound, absent,
                              SPEC_ROOT_REFUSAL)
    _refused_by_every_planner(tmp_path, before, request, binding, bound, empty,
                              POLICY_REFUSAL)
    for key in POLICY_KEYS[letter]:
        def without(spec, key=key):
            del spec["policy"][key]
        _refused_by_every_planner(tmp_path, before, request, binding, bound, without,
                                  POLICY_REFUSAL)
    if letter == "E":
        # A present policy whose only postcondition restates the executor's
        # own report still lacks the independent state-change assertion.
        def self_reported(spec):
            spec["policy"]["postconditions"] = [
                {"path": "outcome.status", "operation": "equals", "value": "ok"}]
        _refused_by_every_planner(tmp_path, before, request, binding, bound, self_reported,
                                  POSTCONDITION_REFUSAL)
    # The unchanged request is still accepted: the refusals were not blanket.
    assert validate_template_request(tmp_path / "host", bound)["status"] == "validated"


@pytest.mark.parametrize("letter", USE_CASES)
def test_missing_host_policy_input_is_refused_before_any_write(tmp_path, letter):
    target = tmp_path / "host"
    request, binding, bound = _bound_request(letter, target)
    before = _tree(target)
    assert set(binding) == {"version", "script", "startup_inputs"}
    assert tuple(binding["startup_inputs"]) == HOST_POLICY_INPUTS
    assert bound["implementation_spec"]["entrypoint_binding"]["startup_inputs"] == (
        binding["startup_inputs"])
    candidates = [({key: value for key, value in binding.items() if key != "startup_inputs"},
                   InputError, BINDING_REFUSAL)]
    for role in HOST_POLICY_INPUTS:
        missing = copy.deepcopy(binding)
        del missing["startup_inputs"][role]
        candidates.append((missing, InputError, BINDING_REFUSAL))
        # A named input that the reviewed console does not define is not
        # replaced by a generated default.
        unresolved = copy.deepcopy(binding)
        unresolved["startup_inputs"][role] = "absent_host_policy"
        candidates.append((unresolved, UnsupportedShape, UNRESOLVED_INPUT_REFUSAL))
    assert len(candidates) == 9
    for candidate, error, reason in candidates:
        _refused(tmp_path, before,
                 lambda: prepare_template_binding(target, request, candidate), error, reason)
        _refused(tmp_path, before,
                 lambda: bind_template(target, request, candidate, tmp_path / "bound"),
                 error, reason)
    assert prepare_template_binding(target, request, binding)["request"] == bound


@pytest.mark.parametrize("letter", USE_CASES)
def test_missing_secret_reference_is_refused_before_any_write(tmp_path, letter):
    target = tmp_path / "host"
    request, binding, bound = _bound_request(letter, target)
    before = _tree(target)

    def configuration(spec):
        rows = [row for row in spec["runtime_files"] if row["kind"] == "configuration"]
        assert len(rows) == 1
        return rows[0]

    reviewed = json.loads(configuration(bound["implementation_spec"])["new_content"])
    assert reviewed["jev_runtime"]["mode"] == "off"
    assert reviewed["jev_runtime"]["credential_ref"] is None

    def rewritten(runtime):
        def mutate(spec):
            configuration(spec)["new_content"] = json.dumps(
                {"jev_runtime": runtime}, separators=(",", ":")) + "\n"
        return mutate

    # No reference key at all, then values that are not references: an inline
    # synthetic value, an empty string and a reference without a name.
    _refused_by_every_planner(tmp_path, before, request, binding, bound,
                              rewritten({"mode": "off", "feature_flag": False}),
                              CREDENTIAL_REFUSAL)
    for value in ("synthetic-inline-value", "", "env:", "env:lowercase_name"):
        _refused_by_every_planner(
            tmp_path, before, request, binding, bound,
            rewritten({"mode": "off", "credential_ref": value, "feature_flag": False}),
            CREDENTIAL_REFUSAL)

    def unreviewed(spec):
        row = configuration(spec)
        spec["runtime_files"].remove(row)
        spec["output"]["permitted_edits"].remove(row["file"])

    _refused_by_every_planner(tmp_path, before, request, binding, bound, unreviewed,
                              CONFIGURATION_REFUSAL)
    # A named reference is accepted without resolving or copying any value.
    referenced = copy.deepcopy(bound)
    rewritten({"mode": "off", "credential_ref": "env:TYPESAFE_API_KEY",
               "feature_flag": False})(referenced["implementation_spec"])
    with pytest.MonkeyPatch.context() as environment:
        environment.delenv("TYPESAFE_API_KEY", raising=False)
        assert validate_template_request(target, referenced)["status"] == "validated"
    assert _tree(target) == before
    assert [path.name for path in tmp_path.iterdir()] == ["host"]

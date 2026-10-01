"""Source-faithful contracts and precise partial installed status for issue 59."""
import importlib.util
import json
from pathlib import Path

import pytest

from jev_integration_evaluator.io import InputError
from jev_integration_evaluator.use_case_templates import inspect_use_case_source, use_case_matrix


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


def test_source_drift_fails_closed(tmp_path):
    row = use_case_matrix()["rows"][1]
    source = tmp_path / row["source"]
    source.parent.mkdir(parents=True)
    source.write_bytes((ROOT / row["source"]).read_bytes() + b"\n# drift\n")
    with pytest.raises(InputError, match="changed"):
        inspect_use_case_source(tmp_path, "L")


def test_retention_adapter_drift_fails_closed(tmp_path):
    row = next(row for row in use_case_matrix()["rows"] if row["id"] == "H")
    source = tmp_path / row["source"]
    source.parent.mkdir(parents=True)
    source.write_bytes((ROOT / row["source"]).read_bytes())
    adapter = tmp_path / row["consumer_adapter"]
    adapter.parent.mkdir(parents=True)
    adapter.write_bytes((ROOT / row["consumer_adapter"]).read_bytes() + b"\n# drift\n")
    with pytest.raises(InputError, match="adapter changed"):
        inspect_use_case_source(tmp_path, "H")


def test_completion_adapter_drift_fails_closed(tmp_path):
    row = next(row for row in use_case_matrix()["rows"] if row["id"] == "E")
    source = tmp_path / row["source"]
    source.parent.mkdir(parents=True)
    source.write_bytes((ROOT / row["source"]).read_bytes())
    adapter = tmp_path / row["consumer_adapter"]
    adapter.parent.mkdir(parents=True)
    adapter.write_bytes((ROOT / row["consumer_adapter"]).read_bytes() + b"\n# drift\n")
    with pytest.raises(InputError, match="adapter changed"):
        inspect_use_case_source(tmp_path, "E")


def test_graph_adapter_drift_fails_closed(tmp_path):
    row = next(row for row in use_case_matrix()["rows"] if row["id"] == "L")
    for key in ("source", "consumer_adapter"):
        path = tmp_path / row[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / row[key]).read_bytes())
    adapter = tmp_path / row["consumer_adapter"]
    adapter.write_bytes(adapter.read_bytes() + b"\n# drift\n")
    with pytest.raises(InputError, match="adapter changed"):
        inspect_use_case_source(tmp_path, "L")


def test_retrieval_adapter_and_corpus_drift_fail_closed(tmp_path):
    row = next(row for row in use_case_matrix()["rows"] if row["id"] == "D")
    assert row["connected_shadow"] == "qualified_offline_d_installed_shadow_protocol"
    assert row["connected_upgrade"] == "pending"
    assert row["provider"] == "pending" and row["benefit"] == "unknown"
    for key in ("source", "consumer_adapter", "consumer_corpus"):
        path = tmp_path / row[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / row[key]).read_bytes())
    adapter = tmp_path / row["consumer_adapter"]
    adapter.write_bytes(adapter.read_bytes() + b"\n# drift\n")
    with pytest.raises(InputError, match="adapter changed"):
        inspect_use_case_source(tmp_path, "D")
    adapter.write_bytes((ROOT / row["consumer_adapter"]).read_bytes())
    corpus = tmp_path / row["consumer_corpus"]
    corpus.write_bytes(corpus.read_bytes() + b" ")
    with pytest.raises(InputError, match="corpus changed"):
        inspect_use_case_source(tmp_path, "D")


def test_claim_adapter_drift_fails_closed(tmp_path):
    row = next(row for row in use_case_matrix()["rows"] if row["id"] == "M")
    for key in ("source", "consumer_adapter"):
        path = tmp_path / row[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / row[key]).read_bytes())
    adapter = tmp_path / row["consumer_adapter"]
    adapter.write_bytes(adapter.read_bytes() + b"\n# drift\n")
    with pytest.raises(InputError, match="adapter changed"):
        inspect_use_case_source(tmp_path, "M")


def test_registered_tool_is_single_host_checked_dispatch():
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


def test_graph_revision_and_approval_are_host_owned():
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


def test_retrieval_missing_and_material_contradiction():
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


def test_completion_ignores_success_flag_without_raw_goal():
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


def test_claim_consumer_rejects_fabrication_and_partial_critical_claim():
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


def test_retention_preserves_pins_bytes_and_explicit_mode():
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

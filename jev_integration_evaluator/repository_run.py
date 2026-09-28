"""A source-bound repository session for the existing single-placement engine.

The command accepts only a fixed offline prepared-input adapter. It never imports
an agent module, evaluates agent text, installs dependencies, or activates a
runtime. Execution requires an exact bundle grant and explicitly trusted host.
A POSIX, owner-private append-only journal is outside the target. Its hash chain
is integrity evidence, not authentication: effectful resume requires a caller-
retained head, supplied separately from the journal. No incomplete operation is
silently replayed. The independently enforced runner remains a separate backend.
"""
from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import stat
import sys
from typing import Any, Iterator
import uuid

from . import capabilities as cap
from .integrations import lifecycle as engine
from .integrations.contracts import validate_spec, validate_inventory
from .integrations.verification import verify_implementation
from .integrations.errors import AmbiguousBinding, MissingBinding, UnsupportedShape
from .runners.isolated_python import (ExecutionGrant, RunnerError, canonical as native_canonical,
                                      inspect_receipt as inspect_native_receipt,
                                      request_digest as native_request_digest, run_schedule,
                                      validate_spec as validate_native_spec)
from .runners.observations import (inspect_baseline_postconditions,
                                   inspect_lifecycle_postconditions)
from .runners.private_archive import (read_private_output_archive,
                                      write_private_output_archive)
from .io import InputError, digest as engine_digest, read_json
from .repository_actions import next_action_contract
from .repository_conclusion import conclude_repository, DEFAULT_OBJECTIVE
from .config import load_config

FORMAT = "repository-session-v1"
ADAPTER = "recorded-reviewed-input-v1"
BOUND_ADAPTER = "recorded-reviewed-input-v2"
MAX_JOURNAL_BYTES = 64_000_000
MAX_RECORD_BYTES = 1_000_000
MAX_INPUT_BYTES = 8_000_000
MAX_EVENTS = 128
OPERATIONS = ("plan", "baseline", "apply", "modified", "rollback")
ZERO_GRANTS = dict(prepare=False, baseline=False, apply=False, modified=False, rollback=False)
DEFAULT_BOUNDS = dict(max_attempts=2, max_events=128, max_cases=64, max_timeout_s=60)
SessionError = cap.CapabilityError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _freeze(value: Any) -> Any:
    raw = cap._json(value)
    if len(raw) > MAX_INPUT_BYTES:
        raise SessionError("session_input_byte_limit")
    return json.loads(raw)


def _exact(obj: Any, keys: set[str], code: str) -> None:
    if type(obj) is not dict or set(obj) != keys:
        raise SessionError(code)


def _sha(value: Any, code: str) -> None:
    if type(value) is not str or not cap.HEX.fullmatch(value):
        raise SessionError(code)


def request_context(*, objective: str | None = None, saved_answers: dict | None = None,
                    policy: cap.DiscoveryPolicy | None = None,
                    bounds: dict | None = None, adapter: str = ADAPTER) -> dict:
    """Caller-owned constraints. None means omitted, not an instruction to clear."""
    if objective is not None and (type(objective) is not str or not objective.strip() or len(objective) > 4000):
        raise SessionError("invalid_objective")
    answers = {} if saved_answers is None else _freeze(saved_answers)
    if type(answers) is not dict or len(cap._json(answers)) > 64_000:
        raise SessionError("invalid_saved_answers")
    selected = cap.DiscoveryPolicy() if policy is None else policy
    if type(selected) is not cap.DiscoveryPolicy:
        raise SessionError("invalid_discovery_policy")
    limits = dict(DEFAULT_BOUNDS) if bounds is None else _freeze(bounds)
    _exact(limits, set(DEFAULT_BOUNDS), "invalid_session_bounds")
    ceilings = dict(max_attempts=3, max_events=MAX_EVENTS, max_cases=64, max_timeout_s=120)
    for key, limit in ceilings.items():
        if type(limits[key]) is not int or not 1 <= limits[key] <= limit:
            raise SessionError("invalid_session_bounds")
    if limits["max_events"] < 16:
        raise SessionError("session_event_bound_too_small")
    if adapter not in (ADAPTER, BOUND_ADAPTER):
        raise SessionError("unsupported_agent_adapter")
    return _freeze(dict(objective=objective, saved_answers=answers,
                        policy=asdict(selected), bounds=limits, adapter=adapter))


def _file_map(report: dict) -> dict:
    return {row["file"]: dict(sha256=row["sha256"], mode=row["mode"]) for row in report["files"]}


def _agent_request(run_id: str | None, repository_identity: str, report_sha256: str,
                   context: dict, source_files: dict) -> dict:
    """Source-bound data to hand to an offline reviewer, never authority."""
    request = dict(schema_version="1.0", kind="repository-agent-request-v1",
                   run_id=run_id, repository_identity=repository_identity,
                   report_sha256=report_sha256, context_sha256=cap._digest(context),
                   objective=context["objective"], saved_answers=copy.deepcopy(context["saved_answers"]),
                   source_files=copy.deepcopy(source_files), adapter=context["adapter"],
                   response_contract=("repository-recorded-reviewed-response-v2"
                                     if context["adapter"] == BOUND_ADAPTER
                                     else "repository-recorded-reviewed-response-v1"),
                   authorization=dict(execution=False, mutation=False, egress=False,
                                      installation=False, publication=False, activation=False))
    cap._schema("repository-agent-request-v1", request)
    return request


def inspect_repository(repo: str | Path, *, context: dict | None = None,
                       capabilities: dict | None = None, coverage_review: dict | None = None,
                       review_sha256: str | None = None, conclusion_config: dict | None = None) -> dict:
    """Path-only entry: no session, bundle, target import, or target mutation."""
    context = request_context() if context is None else _validate_context(context)
    report = cap.discover_repository(repo, cap.DiscoveryPolicy.from_json(context["policy"]))
    supplied_conclusion = any(value is not None for value in
                              (capabilities, coverage_review, review_sha256, conclusion_config))
    if supplied_conclusion:
        if capabilities is None or coverage_review is None or review_sha256 is None:
            raise SessionError("complete_conclusion_inputs_required")
        conclusion = conclude_repository(
            repo, capabilities, load_config() if conclusion_config is None else conclusion_config,
            objective=context["objective"] or DEFAULT_OBJECTIVE,
            review=coverage_review, expected_review_sha256=review_sha256,
            policy=cap.DiscoveryPolicy.from_json(context["policy"]))
        if conclusion["outcome"] == "no_useful_placement":
            status = "no_useful_placement"
            action = "no_further_placement_action"
        elif conclusion["outcome"] == "unsupported_or_unresolved":
            status = ("unsupported" if conclusion["coverage"]["complete_anchored_review"]
                      and conclusion["findings"]
                      and all(row["implementation_support"] == "unsupported"
                              for row in conclusion["findings"])
                      else "insufficient_evidence")
            action = ("review_unsupported_source_shape" if status == "unsupported"
                      else "review_repository_conclusion_and_missing_opinions")
        else:
            status = conclusion["outcome"]
            action = "review_repository_conclusion_and_missing_opinions"
        return dict(schema_version="1.0", kind="repository-run-inspection-v1",
                    status=status, context_sha256=cap._digest(context),
                    report=report, conclusion=conclusion, next_action=action,
                    next_action_contract=next_action_contract(action),
                    agent_request=None,
                    agent_request_sha256=None,
                    review_principal_authenticated=False,
                    target_executed=False, target_modified=False,
                    runtime_activation_authorized=False, benefit_demonstrated=False)
    if not report["coverage"]["complete_within_policy"]:
        status, action = "incomplete_analysis", "resolve_scan_coverage_before_implementation"
    elif report["discovery_outcome"] == "unsupported_or_unresolved":
        status, action = "insufficient_evidence", "review_repository_conclusion_and_missing_opinions"
    else:
        status, action = report["discovery_outcome"], "supply_source_reviewed_inputs"
    agent_request = (_agent_request(None, report["repository_identity"],
                     report["report_sha256"], context, _file_map(report))
                     if action == "supply_source_reviewed_inputs" else None)
    return dict(schema_version="1.0", kind="repository-run-inspection-v1",
                status=status, context_sha256=cap._digest(context),
                report=report, next_action=action,
                next_action_contract=next_action_contract(action),
                agent_request=agent_request,
                agent_request_sha256=cap._digest(agent_request) if agent_request else None,
                target_executed=False, target_modified=False,
                runtime_activation_authorized=False, benefit_demonstrated=False)


def _validate_context(context: dict) -> dict:
    _exact(context, {"objective", "saved_answers", "policy", "bounds", "adapter"}, "invalid_session_context")
    if context["adapter"] not in (ADAPTER, BOUND_ADAPTER):
        raise SessionError("unsupported_agent_adapter")
    return request_context(objective=context["objective"], saved_answers=context["saved_answers"],
                           policy=cap.DiscoveryPolicy.from_json(context["policy"]), bounds=context["bounds"],
                           adapter=context["adapter"])


def _prepared(value: Any) -> dict:
    """Adapter responses are strict data; all bindings still pass engine validation."""
    value = _freeze(value)
    if type(value) is not dict:
        raise SessionError("invalid_prepared_response")
    if value.get("adapter") == BOUND_ADAPTER:
        _exact(value, {"schema_version", "adapter", "request_sha256", "inventory", "spec"}, "invalid_prepared_response")
        contract = "repository-recorded-reviewed-response-v2"
    else:
        _exact(value, {"schema_version", "adapter", "inventory", "spec"}, "invalid_prepared_response")
        contract = "repository-recorded-reviewed-response-v1"
    if value["schema_version"] != "1.0" or value["adapter"] not in (ADAPTER, BOUND_ADAPTER):
        raise SessionError("unsupported_agent_adapter")
    cap._schema(contract, value)
    try:
        value["spec"] = validate_spec(value["spec"])
    except (InputError, KeyError, TypeError, ValueError, RecursionError):
        raise SessionError("invalid_prepared_specification") from None
    return value


def _scope(value: Any, state: dict, head: str | None, existing: bool) -> dict | None:
    if value is None:
        return None
    value = _freeze(value)
    cap._schema("repository-run-scope-v1", value)
    if (value["repository_identity"] != state["repository_identity"] or
            value["context_sha256"] != state["context_sha256"]):
        raise SessionError("scope_context_mismatch")
    # An exact externally retained head authenticates the stored receipt references
    # for this invocation. Merely reading/hash-checking the local journal does not.
    if existing and value["trusted_session_head"] != head:
        raise SessionError("externally_retained_session_head_required")
    if not existing and value["trusted_session_head"] is not None:
        raise SessionError("unexpected_session_head_for_new_run")
    if any(value["grants"][k] for k in ("baseline", "modified")):
        if value["execution_environment"] not in ("trusted_host", "isolated"):
            raise SessionError("execution_environment_required")
        if value["execution_environment"] == "isolated" and value["schema_version"] != "1.1":
            raise SessionError("independent_isolation_backend_unsupported")
    if value["execution_environment"] == "isolated" and value.get("native_contract_sha256") is None:
        raise SessionError("native_contract_anchor_required")
    if (state.get("execution_backend") is not None and
            any(value["grants"][k] for k in ("baseline", "apply", "modified")) and
            value["execution_environment"] != state["execution_backend"]):
        raise SessionError("session_execution_backend_cannot_change")
    return value


def _allowed(scope: dict | None, operation: str, state: dict) -> bool:
    if scope is None or scope["grants"].get("prepare" if operation == "plan" else operation) is not True:
        return False
    if operation == "plan":
        return True
    return bool(state["bundle"] and scope["bundle_digest"] == state["bundle"]["digest"])


def _validate_state(state: dict) -> None:
    cap._schema("repository-session-v1", state)
    if cap._digest(state["context"]) != state["context_sha256"]:
        raise SessionError("session_context_digest_mismatch")
    _validate_context(state["context"])
    if len(state["failures"]) > sum(state["attempts"].values()):
        raise SessionError("invalid_session_failure_history")
    if state.get("decision_epoch", 0) != len(state.get("replan_history", [])):
        raise SessionError("invalid_replan_history")
    if len(state.get("replan_history", [])) > state["context"]["bounds"]["max_attempts"] - 1:
        raise SessionError("invalid_replan_history")


class Journal:
    """Lock + append-only WAL. A torn record is preserved, never auto-truncated."""
    def __init__(self, directory: Path, target: Path):
        if os.name != "posix":
            raise SessionError("unsupported_session_filesystem")
        self.path = Path(os.path.abspath(directory))
        target = Path(os.path.abspath(target))
        if self.path == target or self.path.is_relative_to(target) or target.is_relative_to(self.path):
            raise SessionError("session_must_be_separate_from_target")
        if not self.path.exists():
            # The parent is an explicit, existing caller-selected output location.
            parent, fd = cap._open_directory(self.path.parent)
            try:
                os.mkdir(self.path.name, mode=0o700, dir_fd=fd)
                # A setgid parent can add a special bit despite mode=0700.
                # Normalize only our new directory through its no-follow FD;
                # never chmod a caller's pre-existing session to pass checks.
                created = os.open(self.path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    info = os.fstat(created)
                    if info.st_uid != os.getuid() or not stat.S_ISDIR(info.st_mode):
                        raise SessionError("unsafe_new_session_directory")
                    os.fchmod(created, 0o700)
                    os.fsync(created)
                finally:
                    os.close(created)
                os.fsync(fd)
            finally:
                os.close(fd)
        self.path, self.dirfd = cap._open_directory(self.path)
        self.fd = -1
        try:
            info = os.fstat(self.dirfd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise SessionError("session_directory_must_be_owner_private")
            self.identity = (info.st_dev, info.st_ino)
            self.fd = os.open("journal.jsonl", os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                              0o600, dir_fd=self.dirfd)
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise SessionError("unsafe_session_journal")
            import fcntl
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise SessionError("session_busy") from None
            self.rows = self._read()
            self.state = copy.deepcopy(self.rows[-1]["state"]) if self.rows else None
            self.head = self.rows[-1]["record_sha256"] if self.rows else None
            self.check_receipt_history()
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1
        if self.dirfd >= 0:
            os.close(self.dirfd)
            self.dirfd = -1

    def _identity(self) -> None:
        directory = self.path.stat(follow_symlinks=False)
        entry = os.stat("journal.jsonl", dir_fd=self.dirfd, follow_symlinks=False)
        opened = os.fstat(self.fd)
        if ((directory.st_dev, directory.st_ino) != self.identity or
            not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid() or
            stat.S_IMODE(directory.st_mode) != 0o700 or entry.st_uid != os.getuid() or
            (entry.st_dev, entry.st_ino) != (opened.st_dev, opened.st_ino) or
            entry.st_nlink != 1 or stat.S_IMODE(entry.st_mode) != 0o600):
            raise SessionError("session_storage_identity_changed")

    def _read(self) -> list[dict]:
        self._identity()
        size = os.fstat(self.fd).st_size
        if size > MAX_JOURNAL_BYTES:
            raise SessionError("session_journal_byte_limit")
        raw = os.pread(self.fd, size + 1, 0)
        if len(raw) != size or (raw and not raw.endswith(b"\n")):
            raise SessionError("torn_session_journal_preserved")
        rows, previous = [], None
        for line in raw.splitlines():
            if len(rows) >= MAX_EVENTS or len(line) > MAX_RECORD_BYTES:
                raise SessionError("session_journal_bound")
            try:
                row = json.loads(line)
            except (ValueError, RecursionError, UnicodeError):
                raise SessionError("invalid_session_journal") from None
            _exact(row, {"sequence", "previous", "event", "time", "state", "record_sha256"}, "invalid_session_record")
            saved = row["record_sha256"]
            if (type(row["sequence"]) is not int or row["sequence"] != len(rows) or row["previous"] != previous or
                    saved != cap._digest({k: v for k, v in row.items() if k != "record_sha256"})):
                raise SessionError("session_journal_chain_mismatch")
            if type(row["event"]) is not str or len(row["event"]) > 64 or type(row["time"]) is not str:
                raise SessionError("invalid_session_record")
            _validate_state(row["state"])
            if rows:
                before = rows[-1]["state"]
                for field in ("run_id", "repository_identity", "context_sha256", "context", "source_files", "engine_identity"):
                    if row["state"][field] != before[field]:
                        raise SessionError("session_immutable_context_changed")
                if (before.get("execution_backend") is not None and
                        row["state"].get("execution_backend") != before["execution_backend"]):
                    raise SessionError("session_execution_backend_changed")
                if any(row["state"]["attempts"][op] < before["attempts"][op] for op in OPERATIONS):
                    raise SessionError("session_attempt_history_rewound")
                for field in ("failures", "receipt_history", "authorization_references"):
                    if row["state"][field][:len(before[field])] != before[field]:
                        raise SessionError("session_" + field + "_changed")
            rows.append(row)
            previous = saved
        if rows and len(rows) > rows[-1]["state"]["context"]["bounds"]["max_events"]:
            raise SessionError("session_event_limit")
        return rows

    def check_receipt_history(self) -> None:
        """Archived schedules are immutable references, not replacement approvals."""
        for row in self.state["receipt_history"] if self.state else []:
            self._identity()
            fd = os.open(row["file"], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.dirfd)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
                        or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 64_000_000):
                    raise SessionError("unsafe_archived_execution_receipt")
                hasher, total = hashlib.sha256(), 0
                while True:
                    data = os.read(fd, min(65536, 64_000_001 - total))
                    if not data:
                        break
                    total += len(data)
                    if total > 64_000_000:
                        raise SessionError("archived_receipt_byte_limit")
                    hasher.update(data)
                if total != info.st_size or hasher.hexdigest() != row["sha256"]:
                    raise SessionError("archived_receipt_integrity_mismatch")
            finally:
                os.close(fd)
            if row.get("backend") == "isolated":
                name = row["private_output_file"]
                self._identity()
                try:
                    out = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                  dir_fd=self.dirfd)
                except FileNotFoundError:
                    raise SessionError("native_private_output_missing_no_replay") from None
                try:
                    info = os.fstat(out)
                    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600
                            or not 0 < info.st_size <= 96 * 1024 * 1024):
                        raise SessionError("unsafe_native_private_output")
                    hasher, total = hashlib.sha256(), 0
                    while total <= 96 * 1024 * 1024:
                        data = os.read(out, min(65536, 96 * 1024 * 1024 + 1 - total))
                        if not data:
                            break
                        total += len(data)
                        hasher.update(data)
                    if total != info.st_size or hasher.hexdigest() != row["private_output_sha256"]:
                        raise SessionError("native_private_output_integrity_mismatch")
                finally:
                    os.close(out)

    def room_for_operation(self) -> None:
        limit = self.state["context"]["bounds"]["max_events"]
        if len(self.rows) + 2 > limit or os.fstat(self.fd).st_size + 2 * MAX_RECORD_BYTES > MAX_JOURNAL_BYTES:
            raise SessionError("session_event_limit_before_operation")

    def append(self, state: dict, event: str) -> str:
        self._identity()
        _validate_state(state)
        if len(self.rows) >= state["context"]["bounds"]["max_events"]:
            raise SessionError("session_event_limit")
        row = dict(sequence=len(self.rows), previous=self.head, event=event, time=_now(), state=_freeze(state))
        row["record_sha256"] = cap._digest(row)
        raw = cap._json(row) + b"\n"
        if len(raw) > MAX_RECORD_BYTES or os.fstat(self.fd).st_size + len(raw) > MAX_JOURNAL_BYTES:
            raise SessionError("session_journal_byte_limit")
        offset = 0
        while offset < len(raw):
            written = os.write(self.fd, raw[offset:])
            if written <= 0:
                raise SessionError("session_journal_write_failed")
            offset += written
        os.fsync(self.fd)
        os.fsync(self.dirfd)
        self.rows.append(row)
        self.state, self.head = copy.deepcopy(state), row["record_sha256"]
        return self.head


@contextmanager
def _journal(path: Path, root: Path) -> Iterator[Journal]:
    journal = Journal(path, root)
    try:
        yield journal
    finally:
        journal.close()


def _summary(journal: Journal, status: str, next_action: str, **extra: Any) -> dict:
    state = journal.state
    agent_request = (_agent_request(state["run_id"], state["repository_identity"],
                     state["initial_report_sha256"], state["context"], state["source_files"])
                     if next_action == "supply_recorded_source_reviewed_inventory_and_spec" else None)
    return dict(schema_version="1.0", kind="repository-run-result-v1", status=status,
                run_id=state["run_id"], session_head_sha256=journal.head,
                context_sha256=state["context_sha256"], repository_identity=state["repository_identity"],
                stage=state["stage"], pending_operation=state["pending"], next_action=next_action,
                next_action_contract=next_action_contract(next_action),
                agent_request=agent_request,
                agent_request_sha256=cap._digest(agent_request) if agent_request else None,
                bundle_digest=state["bundle"]["digest"] if state["bundle"] else None,
                receipt_references=copy.deepcopy(state["receipts"]), attempts=copy.deepcopy(state["attempts"]),
                failed_attempts=len(state["failures"]),
                retained_schedules=copy.deepcopy(state["receipt_history"]), constraints_retained=True,
                decision_epoch=state.get("decision_epoch", 0),
                replan_history=copy.deepcopy(state.get("replan_history", [])),
                replan_limit=state["context"]["bounds"]["max_attempts"] - 1,
                snapshot_scope="bounded_source_and_configuration_not_full_repository",
                classification="synthetic_wiring_only", runtime_activation_authorized=False,
                benefit_demonstrated=False, provider_connectivity="not_tested", **extra)


def _engine_bundle(root: Path, path: Path) -> tuple[dict, dict]:
    try:
        _, _, plan, spec, _, _ = engine._load(root, path, current_engine=True)
    except (InputError, OSError, ValueError, KeyError, TypeError, RecursionError):
        raise SessionError("bundle_integrity_or_source_contract_invalid") from None
    return plan, spec


def _check_limits(spec: dict, state: dict) -> None:
    bounds = state["context"]["bounds"]
    if len(spec["verification"]["cases"]) > bounds["max_cases"] or spec["verification"]["timeout_s"] > bounds["max_timeout_s"]:
        raise SessionError("verification_exceeds_session_bounds")


def _native_contract(value: Any, state: dict, plan: dict, scope: dict | None,
                     phase: str | None) -> dict:
    """Bind a reviewed native schedule and independent oracle to this session.

    A local contract hash is only an identity. The caller's authenticated scope
    must supply the exact digest and oracle anchor before any target execution.
    """
    if scope is None or scope["execution_environment"] != "isolated":
        raise SessionError("native_isolation_scope_required")
    contract = _freeze(value)
    _exact(contract, {"schema_version", "kind", "baseline_spec", "modified_spec", "oracle"},
           "invalid_native_contract")
    if contract["schema_version"] != "1.0" or contract["kind"] != "repository-native-contract-v1":
        raise SessionError("unsupported_native_contract")
    cap._schema("repository-native-contract-v1", contract)
    if cap._digest(contract) != scope["native_contract_sha256"]:
        raise SessionError("native_contract_scope_mismatch")
    oracle = contract["oracle"]
    cap._schema("native-postconditions-v1", oracle)
    if cap._digest(oracle) != scope["trusted_oracle_sha256"]:
        raise SessionError("native_oracle_external_anchor_mismatch")
    if any(oracle[k] != wanted for k, wanted in (
            ("repository_identity", state["repository_identity"]),
            ("context_sha256", state["context_sha256"]),
            ("bundle_digest", plan["contract_digest"]))):
        raise SessionError("native_oracle_session_mismatch")
    baseline, modified = contract["baseline_spec"], contract["modified_spec"]
    try:
        validate_native_spec(baseline)
        validate_native_spec(modified)
    except RunnerError as error:
        raise SessionError("invalid_native_runner_spec") from error
    if (baseline["schema_version"] != "1.1" or modified["schema_version"] != "1.1"
            or baseline["environment_identity"] != modified["environment_identity"]
            or baseline["target_environment"] != modified["target_environment"]
            or baseline["source_identity"] != modified["source_identity"]
            or [r["case_id"] for r in baseline["schedule"]] != ["baseline"]
            or [r["case_id"] for r in modified["schedule"]] != ["off", "shadow"]):
        raise SessionError("unsupported_native_schedule_or_environment")
    bound = state["context"]["bounds"]
    if (len(baseline["schedule"]) + len(modified["schedule"]) > bound["max_cases"]
            or any(s["limits"]["schedule_seconds"] > bound["max_timeout_s"]
                   for s in (baseline, modified))):
        raise SessionError("native_schedule_exceeds_session_bounds")
    owned = {row["file"]: row for row in plan["owned_files"]}
    existing_owned = {path for path in owned if path in state["source_files"]}
    if (not owned or existing_owned - {row["path"] for row in baseline["files"]}
            or set(owned) - {row["path"] for row in modified["files"]}):
        raise SessionError("native_spec_omits_owned_source")
    for name, spec in (("baseline", baseline), ("modified", modified)):
        expected = copy.deepcopy(state["source_files"])
        if name == "modified":
            for path, row in owned.items():
                expected[path] = dict(sha256=row["new_sha256"], mode=row["new_mode"])
        for row in spec["files"]:
            if expected.get(row["path"]) != {"sha256": row["sha256"], "mode": row["mode"]}:
                raise SessionError("native_spec_source_mismatch")
        binding = oracle[name]
        if (binding["request_sha256"] != native_request_digest(spec)
                or binding["source_manifest_sha256"] != cap._digest(spec["files"])
                or [r["case_id"] for r in binding["cases"]] != [r["case_id"] for r in spec["schedule"]]):
            raise SessionError("native_oracle_schedule_mismatch")
    if phase is not None and oracle[phase]["attempt"] != state["attempts"][phase] + 1:
        raise SessionError("native_oracle_attempt_mismatch")
    if phase is None and state["receipts"]["baseline"]:
        if oracle["baseline"]["attempt"] != state["attempts"]["baseline"]:
            raise SessionError("native_baseline_attempt_mismatch")
    if phase == "modified" and state["receipts"]["baseline"]:
        if oracle["baseline"]["attempt"] != state["attempts"]["baseline"]:
            raise SessionError("native_baseline_attempt_mismatch")
    if state["receipts"]["modified"] and oracle["modified"]["attempt"] != state["attempts"]["modified"]:
        raise SessionError("native_modified_attempt_mismatch")
    return contract


def _snapshot(root: Path, state: dict, plan: dict | None, *, applied: bool) -> dict:
    report = cap.discover_repository(root, cap.DiscoveryPolicy.from_json(state["context"]["policy"]))
    if report["repository_identity"] != state["repository_identity"]:
        raise SessionError("repository_identity_changed")
    if not report["coverage"]["complete_within_policy"]:
        raise SessionError("incomplete_analysis")
    expected = copy.deepcopy(state["source_files"])
    if applied and plan:
        for row in plan["owned_files"]:
            expected[row["file"]] = dict(sha256=row["new_sha256"], mode=row["new_mode"])
    if _file_map(report) != expected:
        raise SessionError("source_drift_decisions_invalidated")
    return report


def _begin(journal: Journal, operation: str, scope: dict) -> dict:
    state = copy.deepcopy(journal.state)
    if state["attempts"][operation] >= state["context"]["bounds"]["max_attempts"]:
        raise SessionError("operation_retry_limit")
    journal.room_for_operation()
    state["attempts"][operation] += 1
    if operation == "baseline" and state.get("execution_backend") is None:
        state["execution_backend"] = scope["execution_environment"]
    state["pending"] = dict(operation=operation, attempt=state["attempts"][operation],
                            authority_reference=scope["reference"], authority_sha256=cap._digest(scope))
    if scope["execution_environment"] == "isolated" and operation in ("baseline", "modified"):
        state["pending"]["native_contract_sha256"] = scope["native_contract_sha256"]
    state["authorization_references"].append(dict(reference=scope["reference"], sha256=cap._digest(scope)))
    state["stage"] = operation + "_pending"
    journal.append(state, operation + "_started")
    return state


def _archive_receipt(journal: Journal, state: dict, root: Path, bundle: Path,
                     plan: dict, spec: dict, operation: str, receipt_sha256: str, *, recovery: bool = False) -> None:
    """Retain every completed attempt before a later retry can replace its receipt.

    Names are generated from fixed phases, bounded attempt numbers and hashes,
    never target strings. The private copy is exclusive, fsynced and byte-checked.
    A crash leaves unreferenced bytes for inspection; it never removes history.
    """
    receipt = engine._receipt(root, bundle, plan, spec, operation, receipt_sha256)
    filename = f"receipt-{operation}-{state['attempts'][operation]}-{receipt_sha256}.json"
    source = bundle / ("baseline-receipt.json" if operation == "baseline" else "verification-receipt.json")
    journal._identity()
    src = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    dest = -1
    try:
        info = os.fstat(src)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 64_000_000:
            raise SessionError("unsafe_execution_receipt")
        try:
            dest = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=journal.dirfd)
        except FileExistsError:
            if not recovery:
                raise SessionError("unowned_receipt_archive_collision") from None
            old_state = journal.state
            try:
                journal.state = {"receipt_history": [{"file": filename, "sha256": receipt_sha256}]}
                journal.check_receipt_history()
            finally:
                journal.state = old_state
            # Its source was independently checked against the recovery anchor.
            # Reuse matching owned bytes without truncation or an overwrite.
            dest = -1
        hasher, total = hashlib.sha256(), 0
        while True:
            data = os.read(src, min(65536, 64_000_001 - total))
            if not data:
                break
            total += len(data)
            if total > 64_000_000:
                raise SessionError("execution_receipt_byte_limit")
            hasher.update(data)
            offset = 0
            while dest >= 0 and offset < len(data):
                written = os.write(dest, data[offset:])
                if written <= 0:
                    raise SessionError("execution_receipt_write_failed")
                offset += written
        if total != info.st_size or hasher.hexdigest() != receipt_sha256:
            raise SessionError("execution_receipt_changed_during_retention")
        if dest >= 0:
            os.fsync(dest)
        os.fsync(journal.dirfd)
        journal._identity()
    finally:
        os.close(src)
        if dest >= 0:
            os.close(dest)
    state["receipt_history"].append(dict(file=filename, sha256=receipt_sha256,
        phase=operation, attempt=state["attempts"][operation], status=receipt["status"],
        scheduled_cases=receipt["scheduled_cases"], completed_cases=receipt["completed_cases"],
        provenance="externally_retained_recovery_anchor" if recovery else "direct_tool_observation"))


def _native_names(phase: str, attempt: int, receipt_sha256: str) -> tuple[str, str]:
    return (f"receipt-{phase}-{attempt}-{receipt_sha256}.json",
            f"native-output-{phase}-{attempt}-{receipt_sha256}.json")


def _read_native_receipt(journal: Journal, spec: dict, phase: str, attempt: int,
                         trusted_sha256: str) -> dict:
    filename, _ = _native_names(phase, attempt, trusted_sha256)
    journal._identity()
    try:
        fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=journal.dirfd)
    except FileNotFoundError:
        raise SessionError("native_receipt_missing_no_replay") from None
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600
                or not 0 < info.st_size <= MAX_INPUT_BYTES):
            raise SessionError("unsafe_native_receipt_archive")
        raw = os.read(fd, MAX_INPUT_BYTES + 1)
        if len(raw) != info.st_size or os.fstat(fd).st_mtime_ns != info.st_mtime_ns:
            raise SessionError("native_receipt_changed_during_read")
    finally:
        os.close(fd)
    if cap._hash(raw) != trusted_sha256:
        raise SessionError("native_receipt_external_anchor_mismatch")
    try:
        receipt = json.loads(raw)
        inspect_native_receipt(spec, receipt, trusted_receipt_sha256=trusted_sha256)
    except (ValueError, TypeError, RunnerError):
        raise SessionError("invalid_anchored_native_receipt") from None
    return receipt


def _archive_native_result(journal: Journal, state: dict, root: Path, spec: dict,
                           phase: str, result: Any, oracle_sha256: str) -> str:
    attempt = state["attempts"][phase]
    receipt_sha256 = result.receipt_sha256
    receipt_file, output_file = _native_names(phase, attempt, receipt_sha256)
    raw = native_canonical(result.receipt)
    if cap._hash(raw) != receipt_sha256 or len(raw) > MAX_INPUT_BYTES:
        raise SessionError("native_receipt_encoding_invalid")
    journal._identity()
    try:
        fd = os.open(receipt_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=journal.dirfd)
    except FileExistsError:
        raise SessionError("native_receipt_archive_collision_no_replay") from None
    try:
        if os.fstat(fd).st_uid != os.getuid():
            raise SessionError("unsafe_native_receipt_archive")
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise SessionError("native_receipt_archive_write_failed")
            view = view[count:]
        os.fsync(fd)
        os.fsync(journal.dirfd)
    finally:
        os.close(fd)
    archive_sha256 = write_private_output_archive(
        journal.path / output_file, root, spec, result.receipt, result.private_outputs,
        phase=phase, attempt=attempt, trusted_receipt_sha256=receipt_sha256)
    state["receipt_history"].append(dict(
        file=receipt_file, sha256=receipt_sha256, phase=phase, attempt=attempt,
        status="failed", scheduled_cases=result.receipt["scheduled"],
        completed_cases=result.receipt["recorded"], provenance="direct_tool_observation",
        backend="isolated", private_output_file=output_file,
        private_output_sha256=archive_sha256, oracle_sha256=oracle_sha256))
    return archive_sha256


def _native_prior(journal: Journal, root: Path, state: dict, scope: dict,
                  contract: dict, phase: str) -> tuple[dict, dict]:
    reference = state["receipts"][phase]
    if reference is None or reference.get("backend") != "isolated":
        raise SessionError("native_prior_proof_missing")
    trusted_receipt = scope["trusted_" + phase + "_receipt"]
    trusted_output = scope["trusted_" + phase + "_private_output"]
    if (trusted_receipt != reference["sha256"]
            or trusted_output != reference["private_output_sha256"]):
        raise SessionError("native_external_phase_anchor_required")
    history = next((r for r in reversed(state["receipt_history"])
                    if r["phase"] == phase and r["sha256"] == trusted_receipt), None)
    if history is None or history.get("private_output_sha256") != trusted_output:
        raise SessionError("native_phase_history_missing")
    spec = contract[phase + "_spec"]
    receipt = _read_native_receipt(journal, spec, phase, history["attempt"], trusted_receipt)
    expected_authority = f"{state['run_id']}-{phase}-{history['attempt']}"
    if receipt["authority_reference_sha256"] != cap._hash(expected_authority.encode()):
        raise SessionError("native_phase_authority_mismatch")
    if contract["oracle"][phase]["attempt"] != history["attempt"]:
        raise SessionError("native_phase_attempt_mismatch")
    outputs = read_private_output_archive(
        journal.path / history["private_output_file"], root, spec, receipt,
        phase=phase, attempt=history["attempt"], trusted_receipt_sha256=trusted_receipt,
        trusted_archive_sha256=trusted_output)
    return receipt, outputs


def _complete(journal: Journal, state: dict, operation: str, stage: str, failure: str | None = None) -> None:
    if failure:
        state["failures"].append(dict(operation=operation, attempt=state["attempts"][operation], code=failure))
    state["pending"], state["stage"] = None, stage
    journal.append(state, operation + "_completed" if failure is None else operation + "_failed")


def _reconcile(journal: Journal, root: Path, scope: dict | None,
               native_contract: dict | None = None) -> bool:
    """Adopt a proven completed operation; never guess or replay unknown effects."""
    state = copy.deepcopy(journal.state)
    pending = state["pending"]
    if not pending or scope is None:
        return pending is None
    operation = pending["operation"]
    if operation == "plan":
        if not state["planned_output"] or not state["prepared_sha256"]:
            return False
        try:
            prepared_bundle = Path(state["planned_output"])
            _, _, plan, spec, inventory, _ = engine._load(root, prepared_bundle, current_engine=True)
            adapter = state["context"]["adapter"]
            expected = dict(schema_version="1.0", adapter=adapter, inventory=inventory, spec=spec)
            if adapter == BOUND_ADAPTER:
                request = _agent_request(state["run_id"], state["repository_identity"],
                                         state["initial_report_sha256"], state["context"],
                                         state["source_files"])
                expected["request_sha256"] = cap._digest(request)
            if cap._digest(expected) != state["prepared_sha256"]:
                return False
            events = engine._journal(prepared_bundle, plan)
            if not events or events[-1]["event"] != "planned":
                return False
            _snapshot(root, state, None, applied=False)
            _check_limits(spec, state)
            state["bundle"] = dict(path=str(prepared_bundle), digest=plan["contract_digest"])
            _complete(journal, state, operation, "planned")
            return True
        except (InputError, OSError, KeyError, TypeError, ValueError):
            return False
    if not state["bundle"]:
        return False
    bundle = Path(state["bundle"]["path"])
    plan, spec = _engine_bundle(root, bundle)
    if plan["contract_digest"] != state["bundle"]["digest"]:
        raise SessionError("session_bundle_changed")
    if pending.get("native_contract_sha256") is not None:
        phase = operation
        if phase not in ("baseline", "modified") or native_contract is None:
            return False
        if scope["execution_environment"] != "isolated" or scope["native_contract_sha256"] != pending["native_contract_sha256"]:
            return False
        try:
            contract = _native_contract(native_contract, state, plan, scope, None)
            if contract["oracle"][phase]["attempt"] != pending["attempt"]:
                return False
            trusted_receipt = scope["trusted_" + phase + "_receipt"]
            trusted_output = scope["trusted_" + phase + "_private_output"]
            if not trusted_receipt or not trusted_output:
                return False
            native_spec = contract[phase + "_spec"]
            receipt = _read_native_receipt(journal, native_spec, phase, pending["attempt"], trusted_receipt)
            expected_authority = f"{state['run_id']}-{phase}-{pending['attempt']}"
            if receipt["authority_reference_sha256"] != cap._hash(expected_authority.encode()):
                return False
            _, output_file = _native_names(phase, pending["attempt"], trusted_receipt)
            outputs = read_private_output_archive(
                journal.path / output_file, root, native_spec, receipt,
                phase=phase, attempt=pending["attempt"],
                trusted_receipt_sha256=trusted_receipt,
                trusted_archive_sha256=trusted_output)
            _snapshot(root, state, plan, applied=phase == "modified")
            if phase == "baseline":
                report = inspect_baseline_postconditions(
                    contract["oracle"], trusted_oracle_sha256=scope["trusted_oracle_sha256"],
                    spec=native_spec, receipt=receipt, outputs=outputs,
                    trusted_receipt_sha256=trusted_receipt)
            else:
                prior, prior_outputs = _native_prior(journal, root, state, scope, contract, "baseline")
                report = inspect_lifecycle_postconditions(
                    contract["oracle"], trusted_oracle_sha256=scope["trusted_oracle_sha256"],
                    baseline_spec=contract["baseline_spec"], baseline_receipt=prior,
                    baseline_outputs=prior_outputs,
                    trusted_baseline_receipt_sha256=scope["trusted_baseline_receipt"],
                    modified_spec=native_spec, modified_receipt=receipt,
                    modified_outputs=outputs, trusted_modified_receipt_sha256=trusted_receipt)
            passed = bool(report["postconditions_satisfied"] and receipt["source_identity_valid"]
                          and receipt["exited_zero"] == receipt["scheduled"])
            receipt_file, _ = _native_names(phase, pending["attempt"], trusted_receipt)
            state["receipt_history"].append(dict(
                file=receipt_file, sha256=trusted_receipt, phase=phase,
                attempt=pending["attempt"], status="passed" if passed else "failed",
                scheduled_cases=receipt["scheduled"], completed_cases=receipt["recorded"],
                provenance="externally_retained_recovery_anchor", backend="isolated",
                private_output_file=output_file, private_output_sha256=trusted_output,
                oracle_sha256=scope["trusted_oracle_sha256"]))
            if passed:
                state["receipts"][phase] = dict(
                    sha256=trusted_receipt, provenance="externally_retained_recovery_anchor",
                    backend="isolated", private_output_sha256=trusted_output,
                    oracle_sha256=scope["trusted_oracle_sha256"])
                _complete(journal, state, phase, "baseline_passed" if phase == "baseline" else "verified")
            else:
                _complete(journal, state, phase, phase + "_failed", "recovered_native_postconditions_failed")
            return True
        except (RunnerError, SessionError, InputError, OSError, KeyError, TypeError, ValueError):
            return False
    try:
        observed = engine.implementation_status(root, bundle,
            trusted_receipt_sha256=scope["trusted_modified_receipt"] if operation == "modified" else None)
        if operation == "apply" and observed["status"] in ("applied_unverified", "verification_failed"):
            _snapshot(root, state, plan, applied=True)
            _complete(journal, state, operation, "applied_unverified")
            return True
        if operation == "rollback" and observed["status"] == "rolled_back":
            _complete(journal, state, operation, "rolled_back")
            return True
        if operation in ("baseline", "modified"):
            anchor = scope["trusted_" + operation + "_receipt"]
            if not anchor or observed["status"] == "blocked_recovery":
                return False
            receipt = engine._receipt(root, bundle, plan, spec, operation, anchor)
            passed = receipt["status"] == "passed"
            events = [r["event"] for r in engine._journal(bundle, plan)]
            event = ("baseline_verification_passed" if passed else "baseline_verification_failed") if operation == "baseline" else ("verified" if passed else "verification_failed")
            if not events or events[-1] != event:
                return False
            _snapshot(root, state, plan, applied=operation == "modified")
            _archive_receipt(journal, state, root, bundle, plan, spec, operation, anchor, recovery=True)
            if passed:
                state["receipts"][operation] = dict(sha256=anchor, provenance="externally_retained_recovery_anchor")
                _complete(journal, state, operation, "baseline_passed" if operation == "baseline" else "verified")
            else:
                _complete(journal, state, operation, operation + "_failed", "recovered_failed_scheduled_execution")
            return True
    except (InputError, OSError, KeyError, TypeError, ValueError):
        return False
    return False


def _run_native_lifecycle(journal: Journal, root: Path, bundle: Path, plan: dict,
                          scope: dict | None, contract_input: dict | None,
                          retry: bool, stop_after: str | None) -> dict:
    state = journal.state
    if scope is None or scope["execution_environment"] != "isolated" or contract_input is None:
        return _summary(journal, "missing_scope", "supply_exact_native_contract_or_isolation_scope")
    if state["stage"] == "verified":
        contract = _native_contract(contract_input, state, plan, scope, None)
        baseline_receipt, baseline_outputs = _native_prior(journal, root, state, scope, contract, "baseline")
        modified_receipt, modified_outputs = _native_prior(journal, root, state, scope, contract, "modified")
        report = inspect_lifecycle_postconditions(
            contract["oracle"], trusted_oracle_sha256=scope["trusted_oracle_sha256"],
            baseline_spec=contract["baseline_spec"], baseline_receipt=baseline_receipt,
            baseline_outputs=baseline_outputs, trusted_baseline_receipt_sha256=scope["trusted_baseline_receipt"],
            modified_spec=contract["modified_spec"], modified_receipt=modified_receipt,
            modified_outputs=modified_outputs, trusted_modified_receipt_sha256=scope["trusted_modified_receipt"])
        _snapshot(root, state, plan, applied=True)
        if not report["postconditions_satisfied"]:
            return _summary(journal, "blocked_recovery", "review_native_postcondition_failure")
        return _summary(journal, "verified", "software_wiring_only_no_activation",
                        target_executed=True, native_postconditions=report)
    if state["stage"] in ("planned", "baseline_failed"):
        phase = "baseline"
    elif state["stage"] == "baseline_passed":
        phase = "apply"
    elif state["stage"] in ("applied_unverified", "modified_failed"):
        phase = "modified"
    else:
        return _summary(journal, "blocked_recovery", "inspect_native_session_stage")
    if state["stage"] == phase + "_failed" and not retry:
        return _summary(journal, "verification_failed", "review_retained_failure_and_explicitly_request_bounded_retry")
    if not _allowed(scope, phase, state):
        return _summary(journal, "missing_scope", "obtain_exact_bundle_" + phase + "_scope")
    contract = _native_contract(contract_input, state, plan, scope, phase if phase != "apply" else None)
    if phase == "apply":
        baseline_receipt, baseline_outputs = _native_prior(journal, root, state, scope, contract, "baseline")
        baseline_report = inspect_baseline_postconditions(
            contract["oracle"], trusted_oracle_sha256=scope["trusted_oracle_sha256"],
            spec=contract["baseline_spec"], receipt=baseline_receipt,
            outputs=baseline_outputs, trusted_receipt_sha256=scope["trusted_baseline_receipt"])
        if not baseline_report["postconditions_satisfied"]:
            raise SessionError("native_baseline_postconditions_failed")
        _snapshot(root, state, plan, applied=False)
        state = _begin(journal, "apply", scope)
        try:
            engine.apply_native_implementation(
                root, bundle, scope["bundle_digest"], baseline_spec=contract["baseline_spec"],
                baseline_receipt=baseline_receipt, trusted_baseline_sha256=scope["trusted_baseline_receipt"],
                trusted_oracle_sha256=scope["trusted_oracle_sha256"], oracle=contract["oracle"],
                baseline_outputs=baseline_outputs,
                expected_repository_identity=state["repository_identity"],
                expected_context_sha256=state["context_sha256"],
                expected_attempt=state["attempts"]["baseline"],
                expected_authority_sha256=cap._hash(
                    f"{state['run_id']}-baseline-{state['attempts']['baseline']}".encode()))
        except (InputError, OSError, RunnerError, ValueError, KeyError, TypeError):
            _complete(journal, state, "apply", "apply_failed", "native_apply_interrupted_recovery_required")
            return _summary(journal, "blocked_recovery", "reconcile_owned_apply_before_retry")
        _complete(journal, state, "apply", "applied_unverified")
        return _summary(journal, "applied_unverified", "resume_with_externally_retained_session_head")
    _snapshot(root, state, plan, applied=phase == "modified")
    baseline_receipt = baseline_outputs = None
    if phase == "modified":
        baseline_receipt, baseline_outputs = _native_prior(journal, root, state, scope, contract, "baseline")
    state = _begin(journal, phase, scope)
    spec = contract[phase + "_spec"]
    authority = f"{state['run_id']}-{phase}-{state['attempts'][phase]}"
    try:
        result = run_schedule(root, spec, ExecutionGrant(native_request_digest(spec), authority))
        if result.receipt["authority_reference_sha256"] != cap._hash(authority.encode()):
            raise RunnerError("native_authority_reference_mismatch")
        inspect_native_receipt(spec, result.receipt, trusted_receipt_sha256=result.receipt_sha256)
        archive_sha256 = _archive_native_result(journal, state, root, spec, phase, result,
                                                scope["trusted_oracle_sha256"])
        if phase == "baseline":
            report = inspect_baseline_postconditions(
                contract["oracle"], trusted_oracle_sha256=scope["trusted_oracle_sha256"],
                spec=spec, receipt=result.receipt, outputs=result.private_outputs,
                trusted_receipt_sha256=result.receipt_sha256)
        else:
            report = inspect_lifecycle_postconditions(
                contract["oracle"], trusted_oracle_sha256=scope["trusted_oracle_sha256"],
                baseline_spec=contract["baseline_spec"], baseline_receipt=baseline_receipt,
                baseline_outputs=baseline_outputs,
                trusted_baseline_receipt_sha256=scope["trusted_baseline_receipt"],
                modified_spec=spec, modified_receipt=result.receipt,
                modified_outputs=result.private_outputs,
                trusted_modified_receipt_sha256=result.receipt_sha256)
        passed = bool(report["postconditions_satisfied"] and result.receipt["source_identity_valid"]
                      and result.receipt["exited_zero"] == result.receipt["scheduled"])
        if passed:
            _snapshot(root, state, plan, applied=phase == "modified")
        state["receipt_history"][-1]["status"] = "passed" if passed else "failed"
        if passed:
            state["receipts"][phase] = dict(
                sha256=result.receipt_sha256, provenance="direct_tool_observation",
                backend="isolated", private_output_sha256=archive_sha256,
                oracle_sha256=scope["trusted_oracle_sha256"])
    except (RunnerError, InputError, OSError, ValueError, KeyError, TypeError):
        _complete(journal, state, phase, phase + "_failed", "native_execution_or_evidence_interrupted")
        return _summary(journal, "blocked_recovery", "inspect_native_archive_and_external_anchor_before_retry")
    if not passed:
        _complete(journal, state, phase, phase + "_failed", "native_scheduled_postconditions_failed")
        return _summary(journal, "verification_failed", "review_retained_native_schedule_and_postconditions")
    stage = "baseline_passed" if phase == "baseline" else "verified"
    _complete(journal, state, phase, stage)
    return _summary(journal, stage, "resume_with_externally_retained_session_head" if phase == "baseline"
                    else "software_wiring_only_no_activation", target_executed=True,
                    native_postconditions=report)


def run_repository(repo: str | Path, session: str | Path, *, context: dict | None = None,
                   prepared: dict | None = None, bundle: str | Path | None = None,
                   scope: dict | None = None, native_contract: dict | None = None,
                   cancel: bool = False, retry: bool = False,
                   recover: bool = False, replan: bool = False,
                   stop_after: str | None = None) -> dict:
    """Connect planning, baseline, apply, verification, status and owned rollback.

    A supplied context must exactly match an existing run. Omitting it reuses the
    saved answers and constraints; it never clears them. A fresh scope is checked
    for every invocation. A stored grant is provenance, not reusable authority.
    """
    if any(type(value) is not bool for value in (cancel, retry, recover, replan)):
        raise SessionError("invalid_control_flag")
    if replan and (cancel or recover or bundle is not None or retry):
        raise SessionError("incompatible_replan_control")
    if stop_after is not None and stop_after not in OPERATIONS:
        raise SessionError("invalid_stop_stage")
    root, fd, _ = cap._secure_root(repo)
    os.close(fd)
    supplied = _validate_context(context) if context is not None else None
    proposal = _prepared(prepared) if prepared is not None else None
    with _journal(Path(session), root) as journal:
        existing = journal.state is not None
        native_input = _freeze(native_contract) if native_contract is not None else None
        if not existing:
            ctx = supplied or request_context()
            report = cap.discover_repository(root, cap.DiscoveryPolicy.from_json(ctx["policy"]))
            state = dict(schema_version="1.0", kind=FORMAT, run_id=str(uuid.uuid4()),
                         repository_identity=report["repository_identity"], engine_identity=engine.engine_identity(),
                         context=ctx, context_sha256=cap._digest(ctx), source_files=_file_map(report),
                         initial_report_sha256=report["report_sha256"], stage="prepared", pending=None,
                         bundle=None, planned_output=None, prepared_sha256=None, receipts=dict(baseline=None, modified=None),
                         attempts={op: 0 for op in OPERATIONS}, failures=[], receipt_history=[],
                         authorization_references=[], cancelled=False,
                         decision_epoch=0, replan_history=[])
            checked_scope = _scope(scope, state, None, False)
            journal.append(state, "run_created")
            if not report["coverage"]["complete_within_policy"]:
                return _summary(journal, "incomplete_analysis", "resolve_scan_coverage_before_implementation")
        else:
            state = journal.state
            if supplied is not None and supplied != state["context"]:
                raise SessionError("saved_constraints_cannot_be_replaced")
            checked_scope = _scope(scope, state, journal.head, True)
            if state["engine_identity"] != engine.engine_identity():
                raise SessionError("session_engine_changed_requalification_required")
            _, identity_fd, identity = cap._secure_root(root)
            os.close(identity_fd)
            if cap._digest([str(root), identity.st_dev, identity.st_ino]) != state["repository_identity"]:
                raise SessionError("repository_identity_changed")
        if proposal is not None:
            if proposal["adapter"] != journal.state["context"]["adapter"]:
                raise SessionError("prepared_adapter_mismatch")
            if proposal["adapter"] == BOUND_ADAPTER:
                expected_request = _agent_request(
                    journal.state["run_id"], journal.state["repository_identity"],
                    journal.state["initial_report_sha256"], journal.state["context"],
                    journal.state["source_files"])
                if proposal["request_sha256"] != cap._digest(expected_request):
                    raise SessionError("prepared_request_mismatch")
        if cancel:
            state = copy.deepcopy(journal.state)
            state["cancelled"] = True
            journal.append(state, "cancel_requested")
            return _summary(journal, "cancelled", "retain_owned_bundle_for_explicit_recovery")
        if journal.state["cancelled"] and not recover:
            return _summary(journal, "cancelled", "retain_owned_bundle_for_explicit_recovery")
        if replan:
            state = copy.deepcopy(journal.state)
            if (not existing or proposal is None or state["prepared_sha256"] is None
                    or cap._digest(proposal) == state["prepared_sha256"]):
                raise SessionError("replan_requires_changed_reviewed_response")
            if (state["pending"] is not None or state["cancelled"]
                    or any(state["attempts"][op] for op in ("baseline", "apply", "modified", "rollback"))
                    or any(state["receipts"].values())):
                raise SessionError("replan_after_effect_forbidden")
            if (not _allowed(checked_scope, "plan", state)
                    or state["attempts"]["plan"] >= state["context"]["bounds"]["max_attempts"]
                    or len(state.get("replan_history", [])) >= state["context"]["bounds"]["max_attempts"] - 1):
                raise SessionError("replan_scope_or_limit_unavailable")
            if checked_scope.get("prepared_sha256") != cap._digest(proposal):
                raise SessionError("replan_scope_must_bind_exact_prepared_response")
            _snapshot(root, state, None, applied=False)
            try:
                validate_inventory(root, proposal["inventory"], proposal["spec"])
            except (InputError, KeyError, TypeError, ValueError, OSError):
                raise SessionError("replan_review_or_source_invalid") from None
            state.setdefault("replan_history", []).append(dict(
                epoch=state.get("decision_epoch", 0), stage=state["stage"],
                prepared_sha256=state["prepared_sha256"],
                planned_output=state["planned_output"], bundle=copy.deepcopy(state["bundle"]),
                scope_reference=checked_scope["reference"], scope_sha256=cap._digest(checked_scope)))
            state["decision_epoch"] = state.get("decision_epoch", 0) + 1
            state["stage"], state["bundle"], state["planned_output"], state["prepared_sha256"] = "prepared", None, None, None
            journal.append(state, "reviewed_pre_effect_replan_requested")
        if journal.state["pending"] and not recover:
            if not _reconcile(journal, root, checked_scope, native_input):
                if (journal.state["pending"]["operation"] == "plan" and retry and proposal is not None
                        and _allowed(checked_scope, "plan", journal.state)
                        and cap._digest(proposal) == journal.state["prepared_sha256"]):
                    # Planning cannot execute a target. Preserve its interrupted
                    # private output and use a distinct bounded attempt directory.
                    _complete(journal, copy.deepcopy(journal.state), "plan", "plan_failed",
                              "interrupted_read_only_preparation_preserved")
                else:
                    return _summary(journal, "blocked_recovery", "supply_external_receipt_anchor_or_owned_rollback_scope")
        if bundle is not None:
            supplied_bundle = engine._bundle_dir(bundle)
            if journal.state["bundle"]:
                if str(supplied_bundle) != journal.state["bundle"]["path"]:
                    raise SessionError("session_bundle_cannot_be_replaced")
            else:
                plan, spec = _engine_bundle(root, supplied_bundle)
                _check_limits(spec, journal.state)
                state = copy.deepcopy(journal.state)
                state["bundle"] = dict(path=str(supplied_bundle), digest=plan["contract_digest"])
                state["stage"] = "planned"
                journal.append(state, "existing_bundle_attached")
        if proposal is not None and journal.state["prepared_sha256"] is not None:
            if cap._digest(proposal) != journal.state["prepared_sha256"]:
                raise SessionError("prepared_review_changed_fresh_replan_required")
        if journal.state["bundle"] is None:
            if proposal is None:
                return _summary(journal, "insufficient_evidence", "supply_recorded_source_reviewed_inventory_and_spec")
            if not _allowed(checked_scope, "plan", journal.state):
                return _summary(journal, "missing_scope", "obtain_private_bundle_preparation_scope")
            _snapshot(root, journal.state, None, applied=False)
            _check_limits(proposal["spec"], journal.state)
            try:
                validate_inventory(root, proposal["inventory"], proposal["spec"])
            except (InputError, KeyError, TypeError, ValueError, OSError):
                raise SessionError("prepared_source_or_review_invalid") from None
            if journal.state["stage"] == "plan_failed" and not retry:
                return _summary(journal, "preparation_failed", "review_preserved_output_and_explicitly_request_bounded_retry")
            state = copy.deepcopy(journal.state)
            if state["attempts"]["plan"] >= state["context"]["bounds"]["max_attempts"]:
                raise SessionError("operation_retry_limit")
            out = journal.path / ("implementation-bundle-" + str(state["attempts"]["plan"] + 1))
            state["prepared_sha256"], state["planned_output"] = cap._digest(proposal), str(out)
            journal.append(state, "reviewed_preparation_bound")
            state = _begin(journal, "plan", checked_scope)
            try:
                result = engine.plan_implementation(root, proposal["inventory"], proposal["spec"]["candidate_id"], proposal["spec"], out)
            except MissingBinding:
                _complete(journal, state, "plan", "plan_failed", "missing_host_binding")
                return _summary(journal, "missing_prerequisite", "supply_missing_host_binding")
            except AmbiguousBinding:
                _complete(journal, state, "plan", "plan_failed", "ambiguous_host_binding")
                return _summary(journal, "insufficient_evidence", "resolve_ambiguous_host_binding")
            except UnsupportedShape:
                _complete(journal, state, "plan", "plan_failed", "unsupported_source_shape")
                return _summary(journal, "unsupported", "select_supported_source_shape")
            except OSError:
                _complete(journal, state, "plan", "plan_failed", "host_prerequisite_unavailable")
                return _summary(journal, "missing_prerequisite", "resolve_host_prerequisite")
            except (InputError, ValueError, KeyError, TypeError):
                _complete(journal, state, "plan", "plan_failed", "planning_input_invalid")
                return _summary(journal, "insufficient_evidence", "review_invalid_preparation_inputs")
            state["bundle"] = dict(path=str(out), digest=result["bundle_digest"])
            _complete(journal, state, "plan", "planned")
            if stop_after == "plan":
                return _summary(journal, "planned", "review_exact_bundle_and_obtain_execution_mutation_scope")
        state = journal.state
        bundle_path = Path(state["bundle"]["path"])
        plan, spec = _engine_bundle(root, bundle_path)
        if plan["contract_digest"] != state["bundle"]["digest"]:
            raise SessionError("session_bundle_changed")
        _check_limits(spec, state)
        if recover:
            if not _allowed(checked_scope, "rollback", state) or checked_scope["rollback_digest"] != engine.rollback_digest(plan):
                return _summary(journal, "missing_scope", "approve_exact_owned_rollback_digest", rollback_digest=engine.rollback_digest(plan))
            state = _begin(journal, "rollback", checked_scope)
            try:
                engine.rollback_implementation(root, bundle_path, checked_scope["rollback_digest"])
            except (InputError, OSError, ValueError, KeyError, TypeError):
                _complete(journal, state, "rollback", "blocked_recovery", "owned_rollback_refused_or_interrupted")
                return _summary(journal, "blocked_recovery", "preserve_concurrent_edits_and_review_owned_bytes")
            _complete(journal, state, "rollback", "rolled_back")
            return _summary(journal, "rolled_back", "retain_historical_receipts_and_prepare_fresh_review_for_reapplication")
        if state["stage"] == "rolled_back":
            return _summary(journal, "rolled_back", "prepare_fresh_source_review_and_bundle_for_new_run")
        if state["stage"] in ("planned", "baseline_passed", "baseline_failed"):
            _snapshot(root, state, plan, applied=False)
        elif state["stage"] in ("applied_unverified", "modified_failed", "verified"):
            _snapshot(root, state, plan, applied=True)
        try:
            observed = engine.implementation_status(root, bundle_path,
                        trusted_receipt_sha256=state["receipts"]["modified"]["sha256"] if state["receipts"]["modified"] and checked_scope else None)
        except (InputError, OSError, ValueError, KeyError, TypeError):
            return _summary(journal, "blocked_recovery", "inspect_bundle_receipts_and_owned_source")
        if observed["status"] == "blocked_recovery":
            return _summary(journal, "blocked_recovery", "supply_exact_owned_rollback_scope")
        if state.get("execution_backend") == "isolated" or (
                state.get("execution_backend") is None and checked_scope is not None
                and checked_scope["execution_environment"] == "isolated"):
            try:
                return _run_native_lifecycle(journal, root, bundle_path, plan, checked_scope,
                                             native_input, retry, stop_after)
            except (RunnerError, InputError, OSError, ValueError, KeyError, TypeError):
                return _summary(journal, "blocked_recovery", "inspect_native_contract_and_private_archive")
        if state["stage"] == "verified":
            _snapshot(root, state, plan, applied=True)
            if checked_scope is None:
                return _summary(journal, "recorded_untrusted", "supply_externally_retained_session_head")
            if observed["status"] != "verified":
                return _summary(journal, "blocked_recovery", "inspect_stale_or_changed_verification_receipt")
            return _summary(journal, "verified", "software_wiring_only_no_activation", target_executed=False)
        for operation in ("baseline", "apply", "modified"):
            state = journal.state
            if operation == "baseline" and state["receipts"]["baseline"] is not None:
                continue
            if operation == "apply" and observed["status"] in ("applied_unverified", "verification_failed", "verified"):
                continue
            if operation == "modified" and state["receipts"]["modified"] is not None:
                continue
            if state["stage"] == operation + "_failed" and not retry:
                return _summary(journal, "verification_failed", "review_retained_failure_and_explicitly_request_bounded_retry")
            if not _allowed(checked_scope, operation, state):
                return _summary(journal, "missing_scope", "obtain_exact_bundle_" + operation + "_scope")
            _snapshot(root, state, plan, applied=operation == "modified")
            state = _begin(journal, operation, checked_scope)
            try:
                if operation == "apply":
                    if state["receipts"]["baseline"] is None:
                        raise SessionError("trusted_baseline_missing")
                    result = engine.apply_implementation(root, bundle_path, checked_scope["bundle_digest"],
                                baseline_sha256=state["receipts"]["baseline"]["sha256"])
                    stage = "applied_unverified"
                    observed = result
                else:
                    result = verify_implementation(root, bundle_path, operation, approve_execution=True,
                                baseline_sha256=state["receipts"]["baseline"]["sha256"] if operation == "modified" else None)
                    _archive_receipt(journal, state, root, bundle_path, plan, spec, operation, result["receipt_sha256"])
                    success = result["status"] in ("baseline_passed", "verified")
                    if not success:
                        _complete(journal, state, operation, operation + "_failed", "scheduled_verification_failed")
                        return _summary(journal, "verification_failed", "review_retained_schedule_and_independent_assertions")
                    state["receipts"][operation] = dict(sha256=result["receipt_sha256"], provenance="direct_tool_observation")
                    stage = "baseline_passed" if operation == "baseline" else "verified"
            except (InputError, OSError, ValueError, KeyError, TypeError):
                _complete(journal, state, operation, operation + "_failed", "operation_failed_reconcile_before_retry")
                return _summary(journal, "blocked_recovery", "reconcile_existing_bundle_before_any_retry")
            _complete(journal, state, operation, stage)
            if stop_after == operation:
                return _summary(journal, stage, "resume_with_externally_retained_session_head")
        return _summary(journal, "verified", "software_wiring_only_no_activation", target_executed=True)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, json.dumps(dict(status="blocked", reason="invalid_arguments")) + "\n")


def _external(path: Path, root: Path, limit: int = MAX_INPUT_BYTES) -> Any:
    resolved = path.resolve(strict=True)
    target = root.resolve(strict=True)
    if resolved == target or resolved.is_relative_to(target):
        raise SessionError("caller_inputs_must_be_external_to_target")
    return cap._load(path, max_bytes=limit)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("--session", type=Path)
    parser.add_argument("--context", type=Path)
    parser.add_argument("--capabilities", type=Path)
    parser.add_argument("--coverage-review", type=Path)
    parser.add_argument("--review-sha256")
    parser.add_argument("--conclusion-config", type=Path)
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--scope", type=Path)
    parser.add_argument("--native-contract", type=Path)
    parser.add_argument("--cancel", action="store_true")
    parser.add_argument("--retry", action="store_true")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--replan", action="store_true")
    parser.add_argument("--stop-after", choices=OPERATIONS)
    args = parser.parse_args(argv)
    try:
        context = _external(args.context, args.repo) if args.context else None
        if args.session is None:
            if any((args.prepared, args.bundle, args.scope, args.native_contract, args.cancel, args.retry, args.recover, args.replan, args.stop_after)):
                raise SessionError("explicit_external_session_required")
            result = inspect_repository(args.repo, context=context,
                capabilities=_external(args.capabilities, args.repo) if args.capabilities else None,
                coverage_review=_external(args.coverage_review, args.repo) if args.coverage_review else None,
                review_sha256=args.review_sha256,
                conclusion_config=_external(args.conclusion_config, args.repo) if args.conclusion_config else None)
        else:
            if any((args.capabilities, args.coverage_review, args.review_sha256, args.conclusion_config)):
                raise SessionError("conclusion_inputs_are_path_only")
            result = run_repository(args.repo, args.session, context=context,
                prepared=_external(args.prepared, args.repo) if args.prepared else None,
                bundle=args.bundle, scope=_external(args.scope, args.repo) if args.scope else None,
                native_contract=_external(args.native_contract, args.repo) if args.native_contract else None,
                cancel=args.cancel, retry=args.retry, recover=args.recover,
                replan=args.replan, stop_after=args.stop_after)
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        return 3 if result["status"] in ("verification_failed", "blocked_recovery") else 0
    except SessionError as exc:
        print(json.dumps(dict(status="blocked", reason=exc.code)), file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        print(json.dumps(dict(status="blocked", reason="session_input_or_storage_unavailable")), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

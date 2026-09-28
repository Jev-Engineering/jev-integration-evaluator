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
            action = "no_further_placement_action"
        else:
            action = "review_repository_conclusion_and_missing_opinions"
        return dict(schema_version="1.0", kind="repository-run-inspection-v1",
                    status=conclusion["outcome"], context_sha256=cap._digest(context),
                    report=report, conclusion=conclusion, next_action=action,
                    next_action_contract=next_action_contract(action),
                    agent_request=None,
                    agent_request_sha256=None,
                    target_executed=False, target_modified=False,
                    runtime_activation_authorized=False, benefit_demonstrated=False)
    action = ("resolve_scan_coverage_before_implementation"
              if not report["coverage"]["complete_within_policy"]
              else "supply_source_reviewed_inputs")
    agent_request = (_agent_request(None, report["repository_identity"],
                     report["report_sha256"], context, _file_map(report))
                     if action == "supply_source_reviewed_inputs" else None)
    return dict(schema_version="1.0", kind="repository-run-inspection-v1",
                status=report["discovery_outcome"], context_sha256=cap._digest(context),
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
        if value["execution_environment"] != "trusted_host":
            raise SessionError("independent_isolation_backend_unsupported")
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
    state["pending"] = dict(operation=operation, attempt=state["attempts"][operation],
                            authority_reference=scope["reference"], authority_sha256=cap._digest(scope))
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


def _complete(journal: Journal, state: dict, operation: str, stage: str, failure: str | None = None) -> None:
    if failure:
        state["failures"].append(dict(operation=operation, attempt=state["attempts"][operation], code=failure))
    state["pending"], state["stage"] = None, stage
    journal.append(state, operation + "_completed" if failure is None else operation + "_failed")


def _reconcile(journal: Journal, root: Path, scope: dict | None) -> bool:
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
            expected = dict(schema_version="1.0", adapter=ADAPTER, inventory=inventory, spec=spec)
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


def run_repository(repo: str | Path, session: str | Path, *, context: dict | None = None,
                   prepared: dict | None = None, bundle: str | Path | None = None,
                   scope: dict | None = None, cancel: bool = False, retry: bool = False,
                   recover: bool = False, stop_after: str | None = None) -> dict:
    """Connect planning, baseline, apply, verification, status and owned rollback.

    A supplied context must exactly match an existing run. Omitting it reuses the
    saved answers and constraints; it never clears them. A fresh scope is checked
    for every invocation. A stored grant is provenance, not reusable authority.
    """
    if any(type(value) is not bool for value in (cancel, retry, recover)):
        raise SessionError("invalid_control_flag")
    if stop_after is not None and stop_after not in OPERATIONS:
        raise SessionError("invalid_stop_stage")
    root, fd, _ = cap._secure_root(repo)
    os.close(fd)
    supplied = _validate_context(context) if context is not None else None
    proposal = _prepared(prepared) if prepared is not None else None
    with _journal(Path(session), root) as journal:
        existing = journal.state is not None
        if not existing:
            ctx = supplied or request_context()
            report = cap.discover_repository(root, cap.DiscoveryPolicy.from_json(ctx["policy"]))
            state = dict(schema_version="1.0", kind=FORMAT, run_id=str(uuid.uuid4()),
                         repository_identity=report["repository_identity"], engine_identity=engine.engine_identity(),
                         context=ctx, context_sha256=cap._digest(ctx), source_files=_file_map(report),
                         initial_report_sha256=report["report_sha256"], stage="prepared", pending=None,
                         bundle=None, planned_output=None, prepared_sha256=None, receipts=dict(baseline=None, modified=None),
                         attempts={op: 0 for op in OPERATIONS}, failures=[], receipt_history=[],
                         authorization_references=[], cancelled=False)
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
        if journal.state["pending"] and not recover:
            if not _reconcile(journal, root, checked_scope):
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
            except (InputError, OSError, ValueError, KeyError, TypeError):
                _complete(journal, state, "plan", "plan_failed", "planning_failed_no_target_mutation")
                return _summary(journal, "unsupported_or_missing_prerequisite", "review_prepared_bindings_and_source_shape")
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
    parser.add_argument("--cancel", action="store_true")
    parser.add_argument("--retry", action="store_true")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--stop-after", choices=OPERATIONS)
    args = parser.parse_args(argv)
    try:
        context = _external(args.context, args.repo) if args.context else None
        if args.session is None:
            if any((args.prepared, args.bundle, args.scope, args.cancel, args.retry, args.recover, args.stop_after)):
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
                cancel=args.cancel, retry=args.retry, recover=args.recover, stop_after=args.stop_after)
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

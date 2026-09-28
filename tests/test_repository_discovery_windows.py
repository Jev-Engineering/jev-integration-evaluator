"""Native Windows fixtures for bounded, read-only repository discovery."""
from __future__ import annotations

import json
import os
import subprocess
import types
from collections import Counter
from pathlib import Path

import pytest

from jev_integration_evaluator import capabilities as cap
from jev_integration_evaluator import cli
from jev_integration_evaluator import repository_discovery


pytestmark = pytest.mark.skipif(os.name != "nt", reason="native Windows filesystem qualification")


def _scan(root: Path | str, output: Path, capsys, *arguments: str):
    code = cli.main(["repository-discovery", str(root), "--out", str(output), *arguments])
    captured = capsys.readouterr()
    assert not captured.err
    summary = json.loads(captured.out)
    if code:
        return code, summary, None
    report = json.loads(output.read_text(encoding="utf-8"))
    assert summary == {"status": "written", "artifact_sha256": cap._digest(report)}
    return code, summary, report


def _host(tmp_path: Path) -> Path:
    root = tmp_path / "reviewed-repository"
    (root / "src").mkdir(parents=True)
    (root / "src" / "route.py").write_text(
        'raise RuntimeError("TARGET MODULE MUST NOT RUN")\n'
        "def route(x):\n    return x.dispatch()\n",
        encoding="utf-8")
    return root


def test_native_drive_paths_are_deterministic_case_aware_and_source_bound(tmp_path, capsys):
    assert cap._windows_under_root(r"\\?\C:\child", "\\\\?\\C:\\")
    assert not cap._windows_under_root(r"\\?\C:\outside", r"\\?\C:\reviewed")
    root = _host(tmp_path)
    (root / "VENDOR").mkdir()
    (root / "VENDOR" / "ignored.py").write_text("raise AssertionError()\n", encoding="utf-8")
    (root / ".env").write_text("SECRET_SENTINEL=never-read\n", encoding="utf-8")
    first_path, second_path, alias_path, extended_path = (
        tmp_path / f"report-{n}.json" for n in range(4))

    first_code, first_summary, first = _scan(root, first_path, capsys)
    second_code, second_summary, second = _scan(root, second_path, capsys)
    alias_code, alias_summary, alias = _scan(str(root).upper(), alias_path, capsys)
    _, extended = cap._windows_absolute_path(root)
    extended_code, extended_summary, extended_report = _scan(extended, extended_path, capsys)

    assert first_code == second_code == alias_code == extended_code == 0, (
        first_summary, second_summary, alias_summary, extended_summary)
    assert first["report_sha256"] == second["report_sha256"] == alias["report_sha256"] == extended_report["report_sha256"]
    assert [row["file"] for row in first["files"]] == ["src/route.py"]
    assert first["coverage"]["complete_within_policy"] is True
    assert not (tmp_path / "never-read").exists()
    assert str(root) not in first_path.read_text(encoding="utf-8")
    for report_path in (first_path, second_path, alias_path, extended_path):
        acl = subprocess.run(["icacls.exe", str(report_path)], capture_output=True, text=True, check=True)
        assert "OWNER RIGHTS:(F)" in acl.stdout
        assert "BUILTIN\\Users" not in acl.stdout

    original = first_path.read_bytes()
    blocked_code, blocked, _ = _scan(root, first_path, capsys)
    assert blocked_code == 2
    assert blocked == {"status": "blocked", "reason": "output_unavailable_or_exists"}
    assert first_path.read_bytes() == original

    (root / "src" / "route.py").write_text("def route(x):\n    return x.next()\n", encoding="utf-8")
    changed_code, changed_summary, changed = _scan(root, tmp_path / "changed.json", capsys)
    assert changed_code == 0, changed_summary
    assert changed["report_sha256"] != first["report_sha256"]


def test_native_exclusion_patterns_ignore_windows_path_case(tmp_path, capsys):
    root = _host(tmp_path)
    ignored = root / "Source" / "Internal"
    ignored.mkdir(parents=True)
    (ignored / "hidden.py").write_text("def hidden(x):\n    return x.act()\n", encoding="utf-8")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"exclude": ["source/internal/**"]}), encoding="utf-8")

    code, summary, report = _scan(root, tmp_path / "report.json", capsys, "--policy", str(policy))

    assert code == 0, summary
    assert all(row["file"] != "Source/Internal/hidden.py" for row in report["files"])
    assert report["coverage"]["complete_within_policy"] is True
    assert report["coverage"]["excluded_entries"] >= 1


@pytest.mark.parametrize(("policy", "reason"), [
    ({"max_entries": 1}, "entry_budget"),
    ({"max_files": 1}, "file_count_budget"),
])
def test_native_scope_budgets_preserve_incomplete_outcomes(tmp_path, capsys, policy, reason):
    root = _host(tmp_path)
    (root / "second.py").write_text("def second(x):\n    return x.run()\n", encoding="utf-8")
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    code, summary, report = _scan(root, tmp_path / "report.json", capsys,
                                  "--policy", str(policy_path))

    assert code == 0, summary
    assert report["discovery_outcome"] == "incomplete_analysis"
    assert report["coverage"]["complete_within_policy"] is False
    assert any(item["reason"] == reason for item in report["coverage"]["limitations"])


def test_case_colliding_names_fail_closed_as_ambiguous(tmp_path, capsys, monkeypatch):
    root = _host(tmp_path)
    monkeypatch.setattr(cap, "_windows_directory_entries",
                        lambda _fd, _limit: [("Route.py", 1), ("route.py", 2)])

    code, _, report = _scan(root, tmp_path / "report.json", capsys)

    assert code == 0
    assert report["discovery_outcome"] == "incomplete_analysis"
    assert {"path": "", "reason": "case_ambiguous_directory_entries"} in report["coverage"]["limitations"]
    assert report["coverage"]["files_read"] == 0


def test_directory_handle_moved_within_root_is_not_relabelled(tmp_path, monkeypatch):
    root = _host(tmp_path)
    sibling = root / "different-directory"
    sibling.mkdir()
    _, root_directory, _ = cap._secure_windows_root(root)
    _, sibling_io = cap._windows_absolute_path(sibling)
    sibling_fd, _, sibling_final, _ = cap._windows_open_directory(sibling_io)
    os.close(sibling_fd)
    monkeypatch.setattr(cap, "_windows_final_path", lambda _handle: sibling_final)
    notes, counts = [], Counter()

    try:
        rows = list(cap._walk_windows(root_directory, cap.DiscoveryPolicy(), notes, counts))
    finally:
        cap._close_directory(root_directory)

    assert rows == []
    assert {"path": "", "reason": "source_changed_during_discovery"} in notes
    assert counts["stopped"] == 1


def _make_junction(path: Path, target: Path) -> None:
    command = subprocess.list2cmdline(["mklink", "/J", str(path), str(target)])
    result = subprocess.run(["cmd.exe", "/d", "/c", command], capture_output=True, text=True)
    assert result.returncode == 0, "Windows test runner must support local junction creation"


def test_junction_and_symlink_are_reported_without_reading_outside(tmp_path, capsys):
    root = _host(tmp_path)
    outside = tmp_path / "outside-reviewed-root"
    outside.mkdir()
    secret = outside / "escape.py"
    secret.write_text("raise AssertionError('outside source read')\n", encoding="utf-8")
    junction = root / "linked-directory"
    _make_junction(junction, outside)
    cycle_junction = root / "src" / "cycle-junction"
    _make_junction(cycle_junction, root)

    symlink = root / "linked-file.py"
    symlink_created = True
    try:
        os.symlink(str(secret), str(symlink))
    except OSError:
        symlink_created = False
    if os.environ.get("JEV_REQUIRE_WINDOWS_SYMLINKS") == "1":
        assert symlink_created, "Windows CI must provision symbolic-link creation privilege"

    cycle_symlink = root / "src" / "cycle-symlink"
    cycle_symlink_created = True
    try:
        os.symlink(str(root), str(cycle_symlink), target_is_directory=True)
    except OSError:
        cycle_symlink_created = False
    if os.environ.get("JEV_REQUIRE_WINDOWS_SYMLINKS") == "1":
        assert cycle_symlink_created, "Windows CI must provision directory-symlink creation privilege"

    report_code, _, report = _scan(root, tmp_path / "report.json", capsys)
    reasons = {(row["path"], row["reason"]) for row in report["coverage"]["limitations"]}

    assert report_code == 0
    assert ("linked-directory", "junction_excluded") in reasons
    assert ("src/cycle-junction", "junction_excluded") in reasons
    assert "linked-directory/escape.py" not in {row["file"] for row in report["files"]}
    assert not any(row["file"].startswith("src/cycle-junction/") for row in report["files"])
    assert report["coverage"]["complete_within_policy"] is False
    if symlink_created:
        assert ("linked-file.py", "symlink_excluded") in reasons
        assert "linked-file.py" not in {row["file"] for row in report["files"]}
    else:
        assert cap._windows_reparse_reason(types.SimpleNamespace(
            st_file_attributes=0x400, st_reparse_tag=0xA000000C)) == "symlink_excluded"
    if cycle_symlink_created:
        assert ("src/cycle-symlink", "symlink_excluded") in reasons
        assert not any(row["file"].startswith("src/cycle-symlink/") for row in report["files"])
    else:
        assert cap._windows_reparse_reason(types.SimpleNamespace(
            st_file_attributes=0x400, st_reparse_tag=0xA000000C)) == "symlink_excluded"

    root_alias = tmp_path / "root-junction"
    _make_junction(root_alias, root)
    blocked_code, blocked, blocked_report = _scan(root_alias, tmp_path / "blocked.json", capsys)
    assert blocked_code == 2 and blocked_report is None
    assert blocked == {"status": "blocked", "reason": "repository_path_contains_junction"}

    root_symlink = tmp_path / "root-symlink"
    try:
        os.symlink(str(root), str(root_symlink), target_is_directory=True)
    except OSError:
        if os.environ.get("JEV_REQUIRE_WINDOWS_SYMLINKS") == "1":
            raise AssertionError("Windows CI must provision directory-symlink creation privilege")
        assert cap._windows_reparse_reason(types.SimpleNamespace(
            st_file_attributes=0x400, st_reparse_tag=0xA000000C)) == "symlink_excluded"
    else:
        blocked_code, blocked, blocked_report = _scan(root_symlink, tmp_path / "blocked-link.json", capsys)
        assert blocked_code == 2 and blocked_report is None
        assert blocked == {"status": "blocked", "reason": "repository_path_contains_symlink"}


def test_junction_ancestor_cannot_redirect_the_reviewed_root(tmp_path, capsys):
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    root = _host(real_parent)
    alias = tmp_path / "parent-junction"
    _make_junction(alias, real_parent)
    redirected_root = alias / root.name

    code, summary, report = _scan(redirected_root, tmp_path / "blocked.json", capsys)

    assert code == 2 and report is None
    assert summary == {"status": "blocked", "reason": "repository_path_contains_junction"}
    assert not (tmp_path / "blocked.json").exists()


def test_external_input_and_output_reject_junction_ancestors(tmp_path, capsys):
    root = _host(tmp_path)
    external = tmp_path / "external-data"
    external.mkdir()
    (external / "policy.json").write_text("{}", encoding="utf-8")
    alias = tmp_path / "external-alias"
    _make_junction(alias, external)

    input_code, input_summary, input_report = _scan(
        root, tmp_path / "blocked-input.json", capsys,
        "--policy", str(alias / "policy.json"))
    output = alias / "redirected-report.json"
    output_code, output_summary, output_report = _scan(root, output, capsys)

    assert input_code == 2 and input_report is None
    assert input_summary == {"status": "blocked", "reason": "input_unavailable_or_invalid"}
    assert not (tmp_path / "blocked-input.json").exists()
    assert output_code == 2 and output_report is None
    assert output_summary == {"status": "blocked", "reason": "output_path_contains_reparse_point"}
    assert not (external / "redirected-report.json").exists()


def test_access_denied_source_is_a_recorded_incomplete_outcome(tmp_path, capsys):
    root = _host(tmp_path)
    denied = root / "denied.py"
    denied.write_text("SECRET_SENTINEL = 'must not be echoed'\ndef private(x):\n    return x.call()\n",
                      encoding="utf-8")
    account = subprocess.run(["whoami.exe"], capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["icacls.exe", str(denied), "/deny", f"{account}:(RD)"],
                   capture_output=True, text=True, check=True)
    try:
        code, _, report = _scan(root, tmp_path / "report.json", capsys)
    finally:
        subprocess.run(["icacls.exe", str(denied), "/remove:d", account],
                       capture_output=True, text=True, check=True)

    assert code == 0
    assert report["discovery_outcome"] == "incomplete_analysis"
    assert report["coverage"]["complete_within_policy"] is False
    assert {"path": "denied.py", "reason": "access_denied"} in report["coverage"]["limitations"]
    assert "denied.py" not in {row["file"] for row in report["files"]}
    assert "must not be echoed" not in json.dumps(report)


def test_access_denied_directory_is_not_treated_as_empty(tmp_path, capsys):
    root = _host(tmp_path)
    denied_directory = root / "restricted"
    denied_directory.mkdir()
    (denied_directory / "hidden.py").write_text("x=1\n", encoding="utf-8")
    account = subprocess.run(["whoami.exe"], capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["icacls.exe", str(denied_directory), "/deny", f"{account}:(RD)"],
                   capture_output=True, text=True, check=True)
    try:
        code, _, report = _scan(root, tmp_path / "report.json", capsys)
    finally:
        subprocess.run(["icacls.exe", str(denied_directory), "/remove:d", account],
                       capture_output=True, text=True, check=True)

    assert code == 0
    assert report["discovery_outcome"] == "incomplete_analysis"
    assert {"path": "restricted", "reason": "access_denied"} in report["coverage"]["limitations"]
    assert "restricted/hidden.py" not in {row["file"] for row in report["files"]}


def test_long_extended_drive_paths_are_discovered(tmp_path, capsys):
    root = _host(tmp_path)
    parent = root
    for index in range(8):
        parent = parent / (f"segment{index:02d}_" + "x" * 27)
        parent.mkdir()
    long_source = parent / "long_path.py"
    long_source.write_text("def deep(x):\n    return x.select()\n", encoding="utf-8")
    assert len(str(long_source)) > 260

    code, summary, report = _scan(root, tmp_path / "report.json", capsys)

    assert code == 0, summary
    assert "/".join(long_source.relative_to(root).parts) in {row["file"] for row in report["files"]}
    assert report["coverage"]["complete_within_policy"] is True

    long_root_code, long_root_summary, long_root_report = _scan(
        parent, tmp_path / "long-root-report.json", capsys)
    assert long_root_code == 0, long_root_summary
    assert [row["file"] for row in long_root_report["files"]] == ["long_path.py"]


def test_unc_path_has_a_specific_redacted_outcome(tmp_path, capsys):
    unsupported_paths = (
        (r"\\SENSITIVE-SERVER\reviewed-share\repository", "unsupported_unc_path", "SENSITIVE-SERVER"),
        (r"\\?\UNC\SENSITIVE-SERVER\reviewed-share\repository", "unsupported_unc_path", "SENSITIVE-SERVER"),
        (r"\\.\C:\device", "unsupported_device_path", r"\\.\C:\device"),
        (r"\\?\PIPE\SENSITIVE-DEVICE\pipe", "unsupported_device_path", "SENSITIVE-DEVICE"),
        (r"C:drive-relative", "ambiguous_drive_relative_path", "drive-relative"),
        (r"\\?\C:extended-drive-relative", "ambiguous_drive_relative_path", "extended-drive-relative"),
    )
    for index, (path, reason, private_part) in enumerate(unsupported_paths):
        output = tmp_path / f"unused-{index}.json"
        code, summary, report = _scan(path, output, capsys)
        assert code == 2 and report is None
        assert summary == {"status": "blocked", "reason": reason}
        assert private_part not in json.dumps(summary)
        assert not output.exists()


def test_mapped_and_non_ntfs_roots_have_explicit_results(monkeypatch):
    class FakeKernel32:
        drive_type = 3

        def GetDriveTypeW(self, _root):
            return self.drive_type

        def GetVolumeInformationW(self, _root, _name, _name_len, _serial, _component,
                                  _flags, filesystem, _filesystem_len):
            filesystem.value = "ReFS"
            return 1

    import ctypes
    from ctypes import wintypes

    kernel32 = FakeKernel32()
    monkeypatch.setattr(cap, "_windows_api", lambda: (ctypes, wintypes, kernel32))

    with pytest.raises(cap.CapabilityError) as unsupported_filesystem:
        cap._windows_absolute_path(r"C:\repository")
    assert unsupported_filesystem.value.code == "unsupported_windows_filesystem"

    kernel32.drive_type = 4
    with pytest.raises(cap.CapabilityError) as mapped_drive:
        cap._windows_absolute_path(r"Z:\repository")
    assert mapped_drive.value.code == "unsupported_unc_path"
    assert cap._windows_repository_oserror(types.SimpleNamespace(winerror=206)) == "long_path_unavailable"


def test_keyboard_interrupt_returns_blocked_without_artifact(tmp_path, capsys, monkeypatch):
    root = _host(tmp_path)
    output = tmp_path / "interrupted.json"
    original = cap._read_windows_file

    def interrupt(*args, **kwargs):
        original(*args, **kwargs)
        raise KeyboardInterrupt

    monkeypatch.setattr(cap, "_read_windows_file", interrupt)
    code = repository_discovery.main([str(root), "--out", str(output)])
    captured = capsys.readouterr()

    assert code == 130
    assert json.loads(captured.out) == {"status": "blocked", "reason": "discovery_interrupted"}
    assert not captured.err
    assert not output.exists()


def test_outputs_inside_the_reviewed_root_are_rejected(tmp_path, capsys):
    root = _host(tmp_path)
    code, summary, report = _scan(root, root / "report.json", capsys)

    assert code == 2 and report is None
    assert summary == {"status": "blocked", "reason": "output_must_be_outside_repository"}
    assert not (root / "report.json").exists()


def test_output_parent_components_stay_pinned_during_creation(tmp_path):
    parent = tmp_path / "output-parent"
    parent.mkdir()
    moved = tmp_path / "moved-output-parent"
    _, _, _, handles = cap._windows_pin_directory_path(parent, purpose="output")

    try:
        with pytest.raises(OSError):
            os.rename(parent, moved)
    finally:
        for fd in reversed(handles):
            os.close(fd)

    assert parent.is_dir()
    assert not moved.exists()


def test_preparation_stage_rechecks_native_windows_sources(tmp_path, capsys):
    root = tmp_path / "stage-repository"
    root.mkdir()
    (root / "host.py").write_text(
        "def dispatch(x):\n    return x.run()\n\n"
        "def route(x):\n    return dispatch(x)\n", encoding="utf-8")
    report_path, nominations_path, prepared_path = (
        tmp_path / name for name in ("capabilities.json", "nominations.json", "prepared.json"))
    code, _, report = _scan(root, report_path, capsys)
    assert code == 0
    seam = next(item for item in report["seams"] if item["source"]["qualified_symbol"] == "route")
    source = seam["source"]
    nomination = {
        "schema_version": "1.0", "discovery_version": report["discovery_version"],
        "report_sha256": report["report_sha256"], "seam_id": seam["seam_id"],
        "source": source, "pattern": "C", "proposer": "windows-fixture",
        "rationale": "Finite dispatch hypothesis; no authority or benefit is asserted.",
        "evidence": [{key: source[key] for key in ("file", "file_sha256", "start_line", "end_line")}],
    }
    nominations_path.write_text(json.dumps([nomination]), encoding="utf-8")
    code = cli.main(["repository-discovery", str(root), "--stage", "prepare",
                     "--capabilities", str(report_path), "--nominations", str(nominations_path),
                     "--out", str(prepared_path)])
    output = capsys.readouterr()

    assert code == 0, output.out + output.err
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    assert json.loads(output.out) == {
        "status": "written", "artifact_sha256": cap._digest(prepared)}
    assert prepared["semantic_review"] == "required"
    assert prepared["binding_review"] == "not_performed"
    assert all(prepared[key] is False for key in (
        "implementation_verified", "provider_execution_authorized",
        "mutation_authorized", "runtime_activation_authorized"))


def test_capability_and_nomination_commands_use_the_native_backend(tmp_path, capsys):
    root = tmp_path / "capability-repository"
    root.mkdir()
    (root / "host.py").write_text(
        "def dispatch(x):\n    return x.run()\n\n"
        "def route(x):\n    return dispatch(x)\n", encoding="utf-8")
    report_path = tmp_path / "legacy-capabilities.json"
    assert cli.main(["discover-capabilities", "--repo", str(root), "--out", str(report_path)]) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    capsys.readouterr()
    seam = next(item for item in report["seams"] if item["source"]["qualified_symbol"] == "route")
    source = seam["source"]
    nomination_path = tmp_path / "nomination.json"
    nomination_path.write_text(json.dumps({
        "schema_version": "1.0", "discovery_version": report["discovery_version"],
        "report_sha256": report["report_sha256"], "seam_id": seam["seam_id"],
        "source": source, "pattern": "C", "proposer": "windows-fixture",
        "rationale": "Source-matched hypothesis only.",
        "evidence": [{key: source[key] for key in ("file", "file_sha256", "start_line", "end_line")}],
    }), encoding="utf-8")
    admitted_path = tmp_path / "admitted.json"

    assert cli.main(["nominate-candidate", "--repo", str(root), "--nomination", str(nomination_path),
                     "--report-sha256", report["report_sha256"], "--out", str(admitted_path)]) == 0
    admitted = json.loads(admitted_path.read_text(encoding="utf-8"))
    assert json.loads(capsys.readouterr().out)["artifact_sha256"] == cap._digest(admitted)
    assert admitted["status"] == "nominated_pending_semantic_and_binding_review"
    assert admitted["execution_qualified"] is False

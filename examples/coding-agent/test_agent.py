from types import SimpleNamespace
import pytest

from agent import REGISTERED_CAPABILITIES, dispatch_once


class Choice:
    def __init__(self, answer):
        self.answer = answer

    def choose(self, objective, legal):
        assert isinstance(objective, str)
        assert set(legal) == set(REGISTERED_CAPABILITIES)
        return self.answer


class Executor:
    def __init__(self):
        self.calls = []

    def execute_tool(self, name, arguments):
        self.calls.append((name, arguments.copy()))
        return SimpleNamespace(exit_code=0)


def route(proposal, arguments=None, permissions=()):
    executor = Executor()
    result = dispatch_once(Choice("read_file"), executor, "Read a file", REGISTERED_CAPABILITIES,
                           arguments=arguments, granted_permissions=permissions, router=Choice(proposal))
    return result, executor.calls


def test_authorized_registered_choice_uses_original_arguments():
    arguments = {"path": "src/a.py"}
    assert route("read_file", arguments, ("read",)) == (True, [("read_file", arguments)])


def test_unregistered_action_does_not_execute():
    assert route("delete_repo", {"path": "src/a.py"}, ("read", "write")) == (False, [])


def test_permission_denial_does_not_execute():
    assert route("read_file", {"path": "private/a.py"}, ()) == (False, [])


def test_argument_shape_and_type_are_host_enforced():
    for arguments in (None, {}, {"path": 17}, {"path": "a", "extra": "x"}, {"query": "a"}):
        assert route("read_file", arguments, ("read",)) == (False, [])


def test_abstention_and_malformed_choice_do_not_execute():
    for choice in (None, [], {"tool": "read_file"}, 1):
        assert route(choice, {"path": "a"}, ("read",)) == (False, [])


def test_router_timeout_and_provider_error_do_not_execute():
    class FailedChoice:
        def __init__(self, error):
            self.error = error

        def choose(self, objective, legal):
            raise self.error

    for error in (TimeoutError("late"), ConnectionError("offline"), RuntimeError("provider error")):
        executor = Executor()
        assert dispatch_once(FailedChoice(error), executor, "Read a file", REGISTERED_CAPABILITIES,
                             arguments={"path": "a"}, granted_permissions=("read",)) is False
        assert executor.calls == []


def test_executor_error_is_not_recast_as_router_fallback():
    class FailedExecutor:
        def execute_tool(self, name, arguments):
            raise RuntimeError("tool failed")

    with pytest.raises(RuntimeError, match="tool failed"):
        dispatch_once(Choice("read_file"), FailedExecutor(), "Read a file", REGISTERED_CAPABILITIES,
                      arguments={"path": "a"}, granted_permissions=("read",))


def test_study_rejects_altered_fake_executor_arguments(monkeypatch):
    import routing_study

    class TamperedExecutor(routing_study.FakeExecutor):
        def execute_tool(self, name, *arguments):
            return super().execute_tool(name, {"forged": True})

    monkeypatch.setattr(routing_study, "FakeExecutor", TamperedExecutor)
    with pytest.raises(ValueError, match="fake executor postcondition failed"):
        routing_study.evaluate()

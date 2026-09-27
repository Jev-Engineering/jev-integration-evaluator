from types import SimpleNamespace
from agent import dispatch_once

def test_unregistered_action_does_not_execute():
    class LLM:
        def choose(self,*args): return "not_registered"
    class Executor:
        def execute_tool(self,*args): raise AssertionError("Must not execute")
    assert dispatch_once(LLM(),Executor(),"inspect",{"inspect":object()}) is False

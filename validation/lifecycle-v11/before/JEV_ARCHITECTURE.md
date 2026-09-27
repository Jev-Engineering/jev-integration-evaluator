# JEV architecture map

CompleteTech provider-starter

This is a conservative static map. Dynamic dispatch and framework callbacks require review/traces.

| File | Symbol | Parser | Roles | Fan-out | Reachable nodes | Depth lower bound |
|---|---|---|---|---|---|---|
| agent.py | dispatch_once | python_ast | model, tool | 0 | 0 | 0 |
| agent.py | run_steps | python_ast | deterministic, model, observe, plan, tool | 0 | 0 | 0 |
| agent.py | retain_history | python_ast | context, deterministic, model | 0 | 0 | 0 |
| agent.py | distribute | python_ast | agent, model | 0 | 0 | 0 |
| agent.py | review_change | python_ast | review | 0 | 0 | 0 |
| agent.py | publish_proposal | python_ast | model, write | 0 | 0 | 0 |
| agent.py | &lt;module&gt; | python_ast |  | 0 | 0 | 0 |
| test_agent.py | test_unregistered_action_does_not_execute | python_ast | agent, tool | 1 | 1 | 1 |
| test_agent.py | test_unregistered_action_does_not_execute.LLM.choose | python_ast |  | 0 | 0 | 0 |
| test_agent.py | test_unregistered_action_does_not_execute.Executor.execute_tool | python_ast |  | 0 | 0 | 0 |

## Tool/model/retrieval/state and side-effect maps

```json
{
  "flows": {
    "tool": [
      "agent.py::dispatch_once",
      "agent.py::run_steps",
      "test_agent.py::test_unregistered_action_does_not_execute"
    ],
    "model": [
      "agent.py::dispatch_once",
      "agent.py::run_steps",
      "agent.py::retain_history",
      "agent.py::distribute",
      "agent.py::publish_proposal"
    ],
    "retrieve": [],
    "observe": [
      "agent.py::run_steps"
    ],
    "graph": [],
    "context": [
      "agent.py::retain_history"
    ],
    "agent": [
      "agent.py::distribute",
      "test_agent.py::test_unregistered_action_does_not_execute"
    ]
  },
  "side_effects": [
    {
      "node": "agent.py::publish_proposal",
      "calls": [
        {
          "name": "publisher.publish",
          "resolved_name": "publisher.publish",
          "line": 49
        }
      ]
    }
  ],
  "module_map": [
    {
      "file": "agent.py",
      "symbols": [
        "<module>",
        "dispatch_once",
        "distribute",
        "publish_proposal",
        "retain_history",
        "review_change",
        "run_steps"
      ]
    },
    {
      "file": "test_agent.py",
      "symbols": [
        "test_unregistered_action_does_not_execute",
        "test_unregistered_action_does_not_execute.Executor.execute_tool",
        "test_unregistered_action_does_not_execute.LLM.choose"
      ]
    }
  ]
}
```

## Calls and local data flow

See `architecture.json` for exact source lines, assignment reads/calls, branches, loops, exception nodes, resolved static edges, and unresolved calls. No control-flow completeness is implied.

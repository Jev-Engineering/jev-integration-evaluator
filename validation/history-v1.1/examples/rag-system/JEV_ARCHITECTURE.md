# JEV architecture map

CompleteTech provider-starter

This is a conservative static map. Dynamic dispatch and framework callbacks require review/traces.

| File | Symbol | Parser | Roles | Fan-out | Reachable nodes | Depth lower bound |
|---|---|---|---|---|---|---|
| pipeline.py | answer_request | python_ast | model, retrieve | 0 | 0 | 0 |
| pipeline.py | claim_check | python_ast | model | 0 | 0 | 0 |
| pipeline.py | &lt;module&gt; | python_ast |  | 0 | 0 | 0 |

## Tool/model/retrieval/state and side-effect maps

```json
{
  "flows": {
    "tool": [],
    "model": [
      "pipeline.py::answer_request",
      "pipeline.py::claim_check"
    ],
    "retrieve": [
      "pipeline.py::answer_request"
    ],
    "observe": [],
    "graph": [],
    "context": [],
    "agent": []
  },
  "side_effects": [],
  "module_map": [
    {
      "file": "pipeline.py",
      "symbols": [
        "<module>",
        "answer_request",
        "claim_check"
      ]
    }
  ]
}
```

## Calls and local data flow

See `architecture.json` for exact source lines, assignment reads/calls, branches, loops, exception nodes, resolved static edges, and unresolved calls. No control-flow completeness is implied.

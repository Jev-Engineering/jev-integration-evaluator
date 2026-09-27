# JEV architecture map

CompleteTech provider-starter

This is a conservative static map. Dynamic dispatch and framework callbacks require review/traces.

| File | Symbol | Parser | Roles | Fan-out | Reachable nodes | Depth lower bound |
|---|---|---|---|---|---|---|
| entities.py | reconcile | python_ast | graph, model, write | 0 | 0 | 0 |
| entities.py | &lt;module&gt; | python_ast |  | 0 | 0 | 0 |

## Tool/model/retrieval/state and side-effect maps

```json
{
  "flows": {
    "tool": [],
    "model": [
      "entities.py::reconcile"
    ],
    "retrieve": [],
    "observe": [],
    "graph": [
      "entities.py::reconcile"
    ],
    "context": [],
    "agent": []
  },
  "side_effects": [
    {
      "node": "entities.py::reconcile",
      "calls": [
        {
          "name": "graph.merge",
          "resolved_name": "graph.merge",
          "line": 6
        }
      ]
    }
  ],
  "module_map": [
    {
      "file": "entities.py",
      "symbols": [
        "<module>",
        "reconcile"
      ]
    }
  ]
}
```

## Calls and local data flow

See `architecture.json` for exact source lines, assignment reads/calls, branches, loops, exception nodes, resolved static edges, and unresolved calls. No control-flow completeness is implied.

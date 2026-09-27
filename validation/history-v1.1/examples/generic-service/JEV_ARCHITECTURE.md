# JEV architecture map

CompleteTech provider-starter

This is a conservative static map. Dynamic dispatch and framework callbacks require review/traces.

| File | Symbol | Parser | Roles | Fan-out | Reachable nodes | Depth lower bound |
|---|---|---|---|---|---|---|
| service.py | total_with_tax | python_ast | deterministic | 0 | 0 | 0 |
| service.py | order_numbers | python_ast | deterministic | 0 | 0 | 0 |
| service.py | payload_matches | python_ast | deterministic | 0 | 0 | 0 |
| service.py | decode_payload | python_ast | deterministic | 0 | 0 | 0 |
| service.py | exact_permission | python_ast |  | 0 | 0 | 0 |
| service.py | &lt;module&gt; | python_ast |  | 0 | 0 | 0 |

## Tool/model/retrieval/state and side-effect maps

```json
{
  "flows": {
    "tool": [],
    "model": [],
    "retrieve": [],
    "observe": [],
    "graph": [],
    "context": [],
    "agent": []
  },
  "side_effects": [],
  "module_map": [
    {
      "file": "service.py",
      "symbols": [
        "<module>",
        "decode_payload",
        "exact_permission",
        "order_numbers",
        "payload_matches",
        "total_with_tax"
      ]
    }
  ]
}
```

## Calls and local data flow

See `architecture.json` for exact source lines, assignment reads/calls, branches, loops, exception nodes, resolved static edges, and unresolved calls. No control-flow completeness is implied.

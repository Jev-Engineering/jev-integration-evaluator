# JEV architecture map

CompleteTech provider-starter

This is a conservative static map. Dynamic dispatch and framework callbacks require review/traces.

| File | Symbol | Parser | Roles | Fan-out | Reachable nodes | Depth lower bound |
|---|---|---|---|---|---|---|
| route.rs | &lt;file-review&gt; | lexical_review_only |  | 0 | 0 | 0 |
| router.go | &lt;file-review&gt; | lexical_review_only |  | 0 | 0 | 0 |
| router.ts | opaqueSeam | typescript_ast | model, tool | 0 | 0 | 0 |
| router.ts | exactScale | typescript_ast |  | 0 | 0 | 0 |

## Tool/model/retrieval/state and side-effect maps

```json
{
  "flows": {
    "tool": [
      "router.ts::opaqueSeam"
    ],
    "model": [
      "router.ts::opaqueSeam"
    ],
    "retrieve": [],
    "observe": [],
    "graph": [],
    "context": [],
    "agent": []
  },
  "side_effects": [],
  "module_map": [
    {
      "file": "route.rs",
      "symbols": [
        "<file-review>"
      ]
    },
    {
      "file": "router.go",
      "symbols": [
        "<file-review>"
      ]
    },
    {
      "file": "router.ts",
      "symbols": [
        "exactScale",
        "opaqueSeam"
      ]
    }
  ]
}
```

## Calls and local data flow

See `architecture.json` for exact source lines, assignment reads/calls, branches, loops, exception nodes, resolved static edges, and unresolved calls. No control-flow completeness is implied.

# Finite source-owned cancellation binding

For an already reviewed bounded JS/TS recipe C host, an optional specification
binding is `"invocation_options": "hostOptions"`. Its existing source function is:

```javascript
function hostOptions(request) { return {signal: request.signal}; }
```

Ordinary host code creates the AbortController and owns cancellation. The
transform only passes this signal to the native runtime; it does not create
signals, choose authority or perform side effects. Omitting the binding keeps
the original invocation. See the installed offline synthetic fixture in
`tests/test_node_template_installed_selected.py` and
`references/installed-node-synthetic-owner-v1.md` for the exact bounded lifecycle.

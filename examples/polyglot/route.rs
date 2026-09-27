// Review-only lead, not an AST-verified recommendation.
fn choose_recovery(retry: bool) -> &'static str {
    if retry { "inspect" } else { "stop" }
}

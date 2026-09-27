"""Identity evidence remains separate from transaction and merge authority."""
def reconcile(llm, graph, left, right, approval, expected_revision):
    hypothesis = llm.classify(left, right)
    if approval and graph.revision == expected_revision:
        if hypothesis == "same":
            return graph.merge(left, right)
    return None

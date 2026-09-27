"""Read-only injectable retrieval/generation seam; no network client is constructed."""
def answer_request(retriever, llm, query):
    chunks = retriever.retrieve(query)
    answer = llm.generate(query, chunks)
    return answer


def claim_check(llm, request, claims, source_context):
    answer = llm.classify(request, claims, source_context)
    return answer

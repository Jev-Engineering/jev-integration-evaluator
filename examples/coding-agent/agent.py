"""Injectable miniature agent. Scanning never imports or runs this target module.
The deliberately simplistic orchestration is an analysis fixture, not production code.
"""
def dispatch_once(llm, executor, objective, registry):
    proposal = llm.choose(objective, tuple(registry))
    if proposal in registry:
        result = executor.execute_tool(proposal)
        return result.exit_code == 0
    return False


def run_steps(llm, executor, planner, environment, objective, maximum_steps=3):
    plan = planner.plan(objective)
    for step in range(maximum_steps):
        observation = environment.observe()
        try:
            proposal = llm.choose(plan, observation)
            result = executor.execute_tool(proposal)
            if result.success:
                return result
        except RuntimeError:
            plan = planner.plan(objective)
    return None


def retain_history(llm, memory, budget):
    entries = memory.load()
    if len(entries) > budget:
        return memory.prune(llm.choose(entries), budget)
    return entries


def distribute(llm, agents, subtask):
    specialist = llm.choose(subtask, tuple(agents))
    if specialist in agents:
        return agents[specialist](subtask)
    return None


def review_change(reviewer, acceptance_criterion, patch):
    diff = reviewer.get_diff(patch)
    test_results = reviewer.run_tests(patch)
    return reviewer.review(diff, acceptance_criterion, test_results)


def publish_proposal(llm, publisher, request, host_approval):
    draft = llm.generate(request)
    if host_approval:
        publisher.publish(draft)
    return draft

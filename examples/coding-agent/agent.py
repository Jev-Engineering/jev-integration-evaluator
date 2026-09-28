"""Injectable miniature agent. Scanning never imports or runs this target module.

The deliberately small orchestration is an analysis fixture, not production code.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    """Host registered tool contract; descriptions are versioned study inputs."""

    name: str
    version: str
    description: str
    permission: str
    argument_types: tuple[tuple[str, type], ...]


CAPABILITY_REGISTRY_VERSION = "coding-agent-tools-v1"
REGISTERED_CAPABILITIES = {
    "read_file": Capability("read_file", "1", "Read the contents of one known file", "read", (("path", str),)),
    "search_repo": Capability("search_repo", "1", "Find matching text in repository files", "search", (("query", str),)),
    "write_file": Capability("write_file", "1", "Write supplied content to one file", "write", (("path", str), ("content", str))),
}


def admissible(proposal, registry, arguments, granted_permissions):
    """Check current host registry, permissions and exact arguments before execution."""
    if not isinstance(proposal, str) or proposal not in registry:
        return False
    capability = registry[proposal]
    if not isinstance(capability, Capability) or capability.name != proposal:
        return False
    if capability.permission not in granted_permissions or not isinstance(arguments, dict):
        return False
    expected = dict(capability.argument_types)
    if arguments.keys() != expected.keys():
        return False
    return all(type(arguments[key]) is kind for key, kind in expected.items())


def dispatch_once(llm, executor, objective, registry, *, arguments=None,
                  granted_permissions=(), router=None):
    """The router proposes only a name; host checks the original arguments."""
    try:
        proposal = (router if router is not None else llm).choose(objective, tuple(registry))
    except Exception:
        return False
    if admissible(proposal, registry, arguments, granted_permissions):
        result = executor.execute_tool(proposal, arguments)
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

"""``orchestrate`` tool — runs the multi-model orchestrator flow.

Service-gated: only offered when ``orchestrator.enabled`` is true in
config.yaml (toggled from the desktop Orchestrator tab), so it adds no schema
footprint for everyone else. The flow itself lives in ``agent/orchestrator.py``.
"""

import json

from tools.registry import registry, tool_error


def check_orchestrator_requirements() -> bool:
    try:
        from agent.orchestrator import is_enabled

        return is_enabled()
    except Exception:
        return False


def orchestrate_tool(task: str, context: str = "") -> str:
    from agent.orchestrator import run_flow
    from agent.subagent_lifecycle import get_active_subagent_parent

    if not isinstance(task, str) or not task.strip():
        return tool_error("orchestrate requires a non-empty 'task'.")
    parent = get_active_subagent_parent()
    if parent is None:
        return tool_error("orchestrate requires an active agent session.")
    return json.dumps(run_flow(parent, task, context or None), ensure_ascii=False)


ORCHESTRATE_SCHEMA = {
    "name": "orchestrate",
    "description": (
        "Run the user's multi-agent flow: a planner writes a plan, an executor "
        "does the work, then a reviewer and a security & quality verifier check "
        "it, looping back to the executor until they approve. Each stage runs as "
        "a subagent on the model the user assigned to that role. Use when the "
        "user asks to orchestrate a task or run it through the orchestrator flow. "
        "Returns every stage's model, status and report; summarize the outcome "
        "for the user."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The full task, with every requirement the stages need.",
            },
            "context": {
                "type": "string",
                "description": "Optional background: relevant files, constraints, prior decisions.",
            },
        },
        "required": ["task"],
    },
}

registry.register(
    name="orchestrate",
    toolset="orchestrator",
    schema=ORCHESTRATE_SCHEMA,
    handler=lambda args, **kw: orchestrate_tool(args.get("task", ""), args.get("context", "")),
    check_fn=check_orchestrator_requirements,
    emoji="🎼",
)

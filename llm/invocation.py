from dataclasses import dataclass


@dataclass(frozen=True)
class InvocationContent:
    content: str
    record: dict | None = None


class RoleModel:
    """Bind a deterministic role while preserving the Agent-facing model interface."""

    supports_routing_context = True

    def __init__(self, router, role):
        self.router = router
        self.role = role

    def invoke(self, prompt, state=None, validator=None):
        return self.router.invoke(self.role, prompt, state or {}, validator)


def invoke_model(model, prompt, state=None, validator=None):
    if getattr(model, "supports_routing_context", False):
        result = model.invoke(prompt, state or {}, validator)
        return InvocationContent(str(result.content), dict(result.record))
    result = model.invoke(prompt)
    content = result.content if hasattr(result, "content") else str(result)
    return InvocationContent(str(content), None)


def model_state_update(state, records):
    records = [dict(record) for record in records or [] if record]
    if not records:
        return {}
    history = list(state.get("model_routing_history", []) or []) + records
    history = history[-100:]
    usage = {
        key: dict(value)
        for key, value in (state.get("model_usage", {}) or {}).items()
    }
    for record in records:
        trace = record.get("attempt_trace") or [{
            "provider": record.get("provider", "unknown"),
            "model": record.get("model", "unknown"),
            "requests": record.get("attempts", 0),
            "latency_ms": record.get("latency_ms", 0),
        }]
        for item in trace:
            key = f'{item.get("provider", "unknown")}/{item.get("model", "unknown")}'
            aggregate = usage.setdefault(
                key,
                {"requests": 0, "input_tokens": 0, "output_tokens": 0, "latency_ms": 0},
            )
            aggregate["requests"] += int(item.get("requests", 0) or 0)
            aggregate["latency_ms"] += int(item.get("latency_ms", 0) or 0)
        success_key = f'{record.get("provider", "unknown")}/{record.get("model", "unknown")}'
        success_aggregate = usage.setdefault(
            success_key,
            {"requests": 0, "input_tokens": 0, "output_tokens": 0, "latency_ms": 0},
        )
        success_aggregate["input_tokens"] += int(record.get("input_tokens", 0) or 0)
        success_aggregate["output_tokens"] += int(record.get("output_tokens", 0) or 0)
    return {
        "model_route": records[-1],
        "model_routing_history": history,
        "model_usage": usage,
        "model_error": {},
        "tokens": sum(
            int(item.get("input_tokens", 0) or 0)
            + int(item.get("output_tokens", 0) or 0)
            for item in usage.values()
        ),
    }

import os
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelTarget:
    provider: str
    model: str


@dataclass(frozen=True)
class ModelRoute:
    primary: ModelTarget
    fallback: ModelTarget


@dataclass(frozen=True)
class ComplexityResult:
    level: str
    reasons: tuple


@dataclass(frozen=True)
class ModelInvocationResult:
    content: str
    record: dict


class ProviderCallError(RuntimeError):
    def __init__(self, message, error_code="MODEL_PROVIDER_ERROR", retryable=False):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable


class ModelRouteError(RuntimeError):
    def __init__(self, result):
        super().__init__(result.get("error", "model route failed"))
        self.result = result


def _target(provider, model, role, level, kind):
    prefix = f"MODEL_ROUTER_{role.upper()}_{level.upper()}_{kind.upper()}"
    return ModelTarget(
        os.getenv(f"{prefix}_PROVIDER", provider).strip().lower(),
        os.getenv(f"{prefix}_MODEL", model).strip(),
    )


def default_routes():
    values = {
        ("architecture", "simple"): ("deepseek", "deepseek-v4-flash", "glm", "glm-5.2"),
        ("architecture", "standard"): ("deepseek", "deepseek-v4-flash", "glm", "glm-5.2"),
        ("architecture", "complex"): ("deepseek", "deepseek-v4-pro", "kimi", "kimi-k2.5"),
        ("file_planner", "simple"): ("deepseek", "deepseek-v4-flash", "qwen", "qwen3.7-flash"),
        ("file_planner", "standard"): ("deepseek", "deepseek-v4-flash", "qwen", "qwen3.7-flash"),
        ("file_planner", "complex"): ("kimi", "kimi-k2.5", "deepseek", "deepseek-v4-pro"),
        ("coder", "simple"): ("deepseek", "deepseek-v4-flash", "qwen", "qwen3.7-flash"),
        ("coder", "standard"): ("kimi", "kimi-k2.7-code", "qwen", "qwen3-coder-plus"),
        ("coder", "complex"): ("kimi", "kimi-k2.7-code", "qwen", "qwen3-coder-plus"),
        ("test_generator", "simple"): ("kimi", "kimi-k2.7-code-highspeed", "qwen", "qwen3-coder-plus"),
        ("test_generator", "standard"): ("kimi", "kimi-k2.7-code-highspeed", "qwen", "qwen3-coder-plus"),
        ("test_generator", "complex"): ("kimi", "kimi-k2.7-code-highspeed", "qwen", "qwen3-coder-plus"),
        ("reviewer", "simple"): ("deepseek", "deepseek-v4-flash", "glm", "glm-4.5-air"),
        ("reviewer", "standard"): ("deepseek", "deepseek-v4-flash", "glm", "glm-4.5-air"),
        ("reviewer", "complex"): ("glm", "glm-5.2", "deepseek", "deepseek-v4-pro"),
        ("repair", "simple"): ("kimi", "kimi-k2.7-code", "qwen", "qwen3-coder-plus"),
        ("repair", "standard"): ("kimi", "kimi-k2.7-code", "qwen", "qwen3-coder-plus"),
        ("repair", "complex"): ("kimi", "kimi-k2.7-code", "qwen", "qwen3-coder-plus"),
    }
    return {
        key: ModelRoute(
            _target(primary_provider, primary_model, key[0], key[1], "primary"),
            _target(fallback_provider, fallback_model, key[0], key[1], "fallback"),
        )
        for key, (primary_provider, primary_model, fallback_provider, fallback_model) in values.items()
    }


def _count_errors(result):
    if not isinstance(result, dict) or result.get("success", True):
        return 0
    return len(result.get("errors", []) or [])


def _dependency_impact(state):
    value = state.get("dependency_impact", 0)
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    return int(value or 0)


def assess_complexity(role, state):
    state = state or {}
    files = state.get("files", []) or state.get("code", []) or []
    file_count = len(files)
    dependency_impact = _dependency_impact(state)
    repair_count = int(state.get("repair_count", 0) or 0)
    compile_errors = _count_errors(state.get("compile_result", {}))
    test_errors = _count_errors(state.get("test_result", {}))
    reasons = []

    if file_count:
        reasons.append(f"planned_files={file_count}")
    if dependency_impact:
        reasons.append(f"dependency_impact={dependency_impact}")
    if repair_count:
        reasons.append(f"repair_count={repair_count}")
    if compile_errors:
        reasons.append(f"compile_errors={compile_errors}")
    if test_errors:
        reasons.append(f"test_failures={test_errors}")

    if role == "repair":
        complex_route = repair_count >= 1 or compile_errors >= 3 or test_errors >= 2
        return ComplexityResult("complex" if complex_route else "standard", tuple(reasons or ["first_repair"]))
    if role in {"architecture", "file_planner"}:
        if repair_count or dependency_impact >= 6:
            return ComplexityResult("complex", tuple(reasons or ["architecture_replan"]))
        return ComplexityResult("standard", tuple(reasons or ["default_standard"]))
    if role == "coder":
        if file_count >= 4 or dependency_impact >= 6:
            return ComplexityResult("complex", tuple(reasons))
        if file_count <= 1:
            return ComplexityResult("simple", tuple(reasons or ["single_file"]))
        return ComplexityResult("standard", tuple(reasons))
    if role == "test_generator":
        if file_count >= 4 or compile_errors or test_errors:
            return ComplexityResult("complex", tuple(reasons))
        if file_count <= 1:
            return ComplexityResult("simple", tuple(reasons or ["single_file"]))
        return ComplexityResult("standard", tuple(reasons))
    if role == "reviewer":
        if file_count >= 4 or compile_errors >= 3 or test_errors >= 2 or repair_count >= 2:
            return ComplexityResult("complex", tuple(reasons))
        if file_count <= 1 and not compile_errors and not test_errors and not repair_count:
            return ComplexityResult("simple", tuple(reasons or ["single_file_verified"]))
        return ComplexityResult("standard", tuple(reasons or ["default_standard"]))
    raise ValueError(f"unsupported model role: {role}")


def _normalize_response(response):
    if isinstance(response, dict) and "content" in response:
        return str(response["content"]), response.get("usage", {}), bool(response.get("usage_available", False))
    return str(response), {}, False


def _provider_error(error):
    if isinstance(error, ProviderCallError):
        return error
    message = str(error)
    lowered = message.lower()
    if isinstance(error, ValueError) or any(word in lowered for word in ("401", "403", "api key", "authentication")):
        return ProviderCallError(message, "MODEL_CONFIGURATION_ERROR", retryable=False)
    if any(word in lowered for word in ("timeout", "429", "rate limit", "connection", "500", "502", "503", "504")):
        return ProviderCallError(message, "MODEL_TRANSPORT_ERROR", retryable=True)
    return ProviderCallError(message, "MODEL_PROVIDER_ERROR", retryable=False)


class ModelRouter:
    def __init__(self, providers, routes=None):
        self.providers = providers
        self.routes = routes or default_routes()

    def invoke(self, role, prompt, state=None, validator=None):
        complexity = assess_complexity(role, state or {})
        route = self.routes[(role, complexity.level)]
        failures = []
        attempt_trace = []
        any_format_retry = False
        any_transport_retry = False
        total_attempts = 0
        started = time.perf_counter()

        for route_kind, target in (("primary", route.primary), ("fallback", route.fallback)):
            provider = self.providers.get(target.provider)
            if provider is None:
                failures.append({"provider": target.provider, "error_code": "MODEL_PROVIDER_NOT_CONFIGURED"})
                continue
            format_retry_used = False
            transport_retry_used = False
            target_requests = 0
            target_started = time.perf_counter()
            for attempt in range(2):
                total_attempts += 1
                target_requests += 1
                try:
                    current_prompt = prompt
                    if format_retry_used:
                        current_prompt = self._correction_prompt(prompt, failures[-1].get("validation_error", "invalid format"))
                    response = provider.invoke(target.model, current_prompt)
                    content, usage, usage_available = _normalize_response(response)
                    valid, validation_error = self._validate(validator, content)
                    if not valid:
                        failures.append({
                            "provider": target.provider,
                            "model": target.model,
                            "error_code": "MODEL_OUTPUT_FORMAT_ERROR",
                            "validation_error": validation_error,
                        })
                        if not format_retry_used and attempt == 0:
                            format_retry_used = True
                            any_format_retry = True
                            continue
                        break
                    attempt_trace.append({
                        "provider": target.provider,
                        "model": target.model,
                        "route": route_kind,
                        "requests": target_requests,
                        "latency_ms": int((time.perf_counter() - target_started) * 1000),
                    })
                    return ModelInvocationResult(
                        content,
                        {
                            "role": role,
                            "complexity": complexity.level,
                            "reasons": list(complexity.reasons),
                            "provider": target.provider,
                            "model": target.model,
                            "route": route_kind,
                            "attempts": total_attempts,
                            "fallback_used": route_kind == "fallback",
                            "format_retry_used": any_format_retry or format_retry_used,
                            "transport_retry_used": any_transport_retry or transport_retry_used,
                            "status": "success",
                            "latency_ms": int((time.perf_counter() - started) * 1000),
                            "input_tokens": int(usage.get("input_tokens", 0) or 0),
                            "output_tokens": int(usage.get("output_tokens", 0) or 0),
                            "usage_available": usage_available,
                            "error_code": "",
                            "attempt_trace": attempt_trace,
                        },
                    )
                except Exception as error:
                    classified = _provider_error(error)
                    failures.append({
                        "provider": target.provider,
                        "model": target.model,
                        "error_code": classified.error_code,
                    })
                    if classified.retryable and attempt == 0:
                        transport_retry_used = True
                        any_transport_retry = True
                        continue
                    break
            if target_requests and not any(
                item.get("provider") == target.provider and item.get("route") == route_kind
                for item in attempt_trace
            ):
                attempt_trace.append({
                    "provider": target.provider,
                    "model": target.model,
                    "route": route_kind,
                    "requests": target_requests,
                    "latency_ms": int((time.perf_counter() - target_started) * 1000),
                })

        result = {
            "role": role,
            "complexity": complexity.level,
            "reasons": list(complexity.reasons),
            "status": "error",
            "attempts": total_attempts,
            "fallback_used": True,
            "error_code": "MODEL_ROUTE_FAILED",
            "error": "primary and fallback model routes failed",
            "failures": failures,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "attempt_trace": attempt_trace,
        }
        raise ModelRouteError(result)

    @staticmethod
    def _validate(validator, content):
        if validator is None:
            return bool(content.strip()), "empty model response"
        result = validator(content)
        if isinstance(result, tuple):
            return bool(result[0]), str(result[1] if len(result) > 1 else "invalid model response")
        return bool(result), "invalid model response"

    @staticmethod
    def _correction_prompt(original_prompt, error):
        return (
            f"{original_prompt}\n\n"
            f"The previous response violated the required output format: {error}. "
            "Return only one complete response in the requested format, without commentary."
        )

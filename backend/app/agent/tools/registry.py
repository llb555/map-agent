"""Unified async tool registry with provider-based validation and execution routing."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from pydantic_core import ErrorDetails

from app.agent.tools.base import ToolDescriptor, ToolInputValidationError, ToolProvider
from app.agent.tools.builtin.provider import BuiltinToolProvider
from app.agent.tools.mcp_gateway import MCPToolGateway
from app.agent.tools.permission import ToolPermissionChecker, ToolPermissionError


@dataclass(frozen=True)
class ToolRuntimePolicy:
    """Per-tool runtime governance policy."""

    timeout_seconds: float = 10.0
    max_retries: int = 0
    circuit_breaker_failures: int = 3
    circuit_breaker_recovery_seconds: float = 30.0
    budget_group: str | None = None
    max_calls_per_run: int | None = None


@dataclass
class _CircuitState:
    failures: int = 0
    opened_at: float | None = None


@dataclass(frozen=True)
class ToolExecutionResult:
    """Normalized tool execution output."""

    call_id: str
    tool_name: str
    status: str
    output: dict[str, Any]
    error_message: str | None = None
    trace_id: str | None = None
    tool_trace_id: str | None = None
    attempt_count: int = 0
    duration_ms: float = 0.0
    fallback_reason: str | None = None
    governance: dict[str, Any] | None = None


_DEFAULT_BUDGET_LIMITS: dict[str, int] = {
    "search": 6,
    "knowledge": 2,
    "map": 4,
    "navigation": 3,
    "orchestration": 4,
    "summary": 4,
}


_DEFAULT_TOOL_POLICIES: dict[str, ToolRuntimePolicy] = {
    "db_query_tool": ToolRuntimePolicy(timeout_seconds=5.0, budget_group="search", max_calls_per_run=6),
    "knowledge_search_tool": ToolRuntimePolicy(
        timeout_seconds=8.0,
        max_retries=1,
        budget_group="knowledge",
        max_calls_per_run=2,
    ),
    "geo_resolve_tool": ToolRuntimePolicy(timeout_seconds=3.0, budget_group="map", max_calls_per_run=3),
    "location_resolve_tool": ToolRuntimePolicy(
        timeout_seconds=6.0,
        max_retries=1,
        budget_group="map",
        max_calls_per_run=3,
    ),
    "route_plan_tool": ToolRuntimePolicy(
        timeout_seconds=8.0,
        max_retries=1,
        budget_group="navigation",
        max_calls_per_run=3,
    ),
    "invoke_worker": ToolRuntimePolicy(timeout_seconds=2.0, budget_group="orchestration", max_calls_per_run=4),
    "summary_tool": ToolRuntimePolicy(timeout_seconds=3.0, budget_group="summary", max_calls_per_run=4),
    "mcp__*": ToolRuntimePolicy(timeout_seconds=10.0, max_retries=1, budget_group="map", max_calls_per_run=4),
}


class ToolRegistry:
    """Provider-oriented runtime entrypoint for builtin and MCP tools.
    面向提供程序的运行时入口，用于内置和 MCP 工具。
    This registry aggregates tools from multiple providers, 
    applies permission checks, validates input against provider-declared JSON Schemas, 
    and routes execution to the appropriate provider implementation.
    该注册表聚合来自多个提供程序的工具，应用权限检查，
    根据提供程序声明的 JSON Schema 验证输入，并将执行路由到适当的提供程序实现。 """

    def __init__(
        self,
        *,
        providers: list[ToolProvider] | None = None,
        permission_checker: ToolPermissionChecker,
        strict_schema: bool = True,
        tool_policies: dict[str, ToolRuntimePolicy] | None = None,
        budget_limits: dict[str, int] | None = None,
        **legacy_dependencies: Any,
    ) -> None:
        self._permission_checker = permission_checker
        self._strict_schema = strict_schema
        self._tool_policies = {
            **_DEFAULT_TOOL_POLICIES,
            **(tool_policies or {}),
        }
        self._budget_limits = {
            **_DEFAULT_BUDGET_LIMITS,
            **(budget_limits or {}),
        }
        self._circuit_breakers: dict[str, _CircuitState] = {}
        self._providers = list(
            providers or self._build_legacy_providers(legacy_dependencies=legacy_dependencies)
        )

    async def get_tools(self, *, allowed_tools: list[str] | None = None) -> dict[str, ToolDescriptor]:
        tools, _ = await self._collect_tools()
        if allowed_tools is None:
            return tools
        return {
            name: descriptor
            for name, descriptor in tools.items()
            if self._matches_allowed_tools(name, allowed_tools)
        }

    async def gettools(self, *, allowed_tools: list[str] | None = None) -> dict[str, ToolDescriptor]:
        """Compatibility alias for provider-aggregated tool discovery.
        用于提供程序聚合工具发现的兼容性别名。"""
        return await self.get_tools(allowed_tools=allowed_tools)

    async def tool_definitions(self, *, allowed_tools: list[str]) -> list[dict[str, Any]]:
        """Return the tool definitions for the tools matching the allowed patterns, including their JSON Schemas.
        返回与允许的模式匹配的工具的工具定义，包括它们的 JSON Schema。"""
        tools = await self.get_tools()
        definitions: list[dict[str, Any]] = []
        seen: set[str] = set()
        for pattern in allowed_tools:
            matched_names = [name for name in tools if fnmatchcase(name, pattern)]
            if any(token in pattern for token in "*?["):
                matched_names.sort()
            for name in matched_names:
                if name in seen:
                    continue
                descriptor = tools[name]
                definitions.append(self._definition_from_descriptor(descriptor))
                seen.add(name)
        return definitions

    async def refresh_tools(self) -> None:
        for provider in self._providers:
            await provider.refresh()

    async def refresh_mcp_tools(self) -> None:
        for provider in self._providers:
            if provider.provider_name == "mcp":
                await provider.refresh()

    def provider_health(self) -> dict[str, Any]:
        return {
            provider.provider_name: provider.health()
            for provider in self._providers
        }

    def mcp_health(self) -> dict[str, Any]:
        for provider in self._providers:
            if provider.provider_name == "mcp":
                return provider.health()
        return {
            "enabled": False,
            "discovered_tool_count": 0,
            "servers": {},
        }

    async def execute(
        self,
        *,
        call_id: str,
        tool_name: str,
        raw_arguments: dict[str, Any],
        allowed_tools: list[str],
        runtime_context: dict[str, Any] | None = None,
    ) -> ToolExecutionResult:
        trace_id = self._trace_id(runtime_context)
        tool_trace_id = f"{trace_id}:{call_id}"
        start = time.monotonic()
        policy = self._policy_for_tool(tool_name)
        governance = self._governance_payload(policy=policy)
        try:
            # Perform permission check before any other processing to fail fast on unauthorized access.
            # 在任何其他处理之前执行权限检查，以便在未经授权访问时快速失败。
            self._permission_checker.ensure_allowed(tool_name=tool_name, allowed_tools=allowed_tools)
            budget_error = self._consume_budget(
                tool_name=tool_name,
                policy=policy,
                runtime_context=runtime_context,
            )
            if budget_error is not None:
                return self._failed(
                    call_id=call_id,
                    tool_name=tool_name,
                    error_type="budget_exceeded",
                    message=budget_error,
                    trace_id=trace_id,
                    tool_trace_id=tool_trace_id,
                    duration_ms=self._elapsed_ms(start),
                    governance=governance,
                )
            circuit_error = self._circuit_error(tool_name=tool_name, policy=policy)
            if circuit_error is not None:
                return self._failed(
                    call_id=call_id,
                    tool_name=tool_name,
                    error_type="circuit_open",
                    message=circuit_error,
                    trace_id=trace_id,
                    tool_trace_id=tool_trace_id,
                    duration_ms=self._elapsed_ms(start),
                    governance=governance,
                )
            tools, owners = await self._collect_tools()
            descriptor = tools.get(tool_name)
            provider = owners.get(tool_name)
            if descriptor is None or provider is None:
                raise ValueError(f"unknown_tool:{tool_name}")
            validated = raw_arguments
            if descriptor.validator is not None:
                validated = descriptor.validator(raw_arguments)

            result, attempts = await self._execute_with_policy(
                provider=provider,
                tool_name=tool_name,
                raw_arguments=raw_arguments,
                validated_arguments=validated,
                policy=policy,
            )
            duration_ms = self._elapsed_ms(start)
            fallback_reason = _extract_fallback_reason(result.output)
            if result.status == "completed":
                self._record_circuit_success(tool_name)
            else:
                self._record_circuit_failure(tool_name, policy=policy)
            return ToolExecutionResult(
                call_id=call_id,
                tool_name=tool_name,
                status=result.status,
                output=result.output,
                error_message=result.error_message,
                trace_id=trace_id,
                tool_trace_id=tool_trace_id,
                attempt_count=attempts,
                duration_ms=duration_ms,
                fallback_reason=fallback_reason,
                governance={
                    **governance,
                    "budget": self._budget_snapshot(runtime_context),
                },
            )
        except ToolPermissionError as exc:
            return self._failed(
                call_id=call_id,
                tool_name=tool_name,
                error_type="permission_error",
                message=str(exc),
                trace_id=trace_id,
                tool_trace_id=tool_trace_id,
                duration_ms=self._elapsed_ms(start),
                governance=governance,
            )
        except ValidationError as exc:
            return self._failed(
                call_id=call_id,
                tool_name=tool_name,
                error_type="validation_error",
                message=str(exc),
                details=exc.errors(),
                trace_id=trace_id,
                tool_trace_id=tool_trace_id,
                duration_ms=self._elapsed_ms(start),
                governance=governance,
            )
        except ToolInputValidationError as exc:
            return self._failed(
                call_id=call_id,
                tool_name=tool_name,
                error_type="validation_error",
                message=str(exc),
                details=exc.details,
                trace_id=trace_id,
                tool_trace_id=tool_trace_id,
                duration_ms=self._elapsed_ms(start),
                governance=governance,
            )
        except TimeoutError as exc:
            self._record_circuit_failure(tool_name, policy=policy)
            return self._failed(
                call_id=call_id,
                tool_name=tool_name,
                error_type="timeout",
                message=str(exc),
                trace_id=trace_id,
                tool_trace_id=tool_trace_id,
                duration_ms=self._elapsed_ms(start),
                governance=governance,
            )
        except Exception as exc:  # pragma: no cover
            self._record_circuit_failure(tool_name, policy=policy)
            return self._failed(
                call_id=call_id,
                tool_name=tool_name,
                error_type="runtime_error",
                message=str(exc),
                trace_id=trace_id,
                tool_trace_id=tool_trace_id,
                duration_ms=self._elapsed_ms(start),
                governance=governance,
            )

    async def _execute_with_policy(
        self,
        *,
        provider: ToolProvider,
        tool_name: str,
        raw_arguments: dict[str, Any],
        validated_arguments: Any | None,
        policy: ToolRuntimePolicy,
    ) -> tuple[Any, int]:
        attempts = 0
        last_error: Exception | None = None
        max_attempts = max(1, policy.max_retries + 1)
        for attempt in range(1, max_attempts + 1):
            attempts = attempt
            try:
                result = await asyncio.wait_for(
                    provider.execute(
                        tool_name=tool_name,
                        raw_arguments=raw_arguments,
                        validated_arguments=validated_arguments,
                    ),
                    timeout=max(0.1, policy.timeout_seconds),
                )
                if result.status == "completed" or attempt >= max_attempts:
                    return result, attempts
            except TimeoutError as exc:
                last_error = exc
                if attempt >= max_attempts:
                    raise TimeoutError(f"tool_timeout:{tool_name}:{policy.timeout_seconds}s") from exc
            except Exception as exc:
                last_error = exc
                if attempt >= max_attempts:
                    raise
            await asyncio.sleep(min(0.2 * attempt, 0.8))
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"tool_execution_failed:{tool_name}")

    def _build_legacy_providers(self, *, legacy_dependencies: dict[str, Any]) -> list[ToolProvider]:
        """Build providers based on legacy dependencies, supporting both direct service instances and factory-based specifications.
        根据传统依赖关系构建提供程序，支持直接服务实例和基于工厂的规范。"""
        legacy = dict(legacy_dependencies)
        mcp_tool_gateway = legacy.pop("mcp_tool_gateway", None) or MCPToolGateway()
        builtin_services = {
            key: legacy.pop(key)
            for key in (
                "db_query_tool",
                "geo_resolve_tool",
                "route_plan_tool",
                "summary_tool",
            )
            if key in legacy
        }
        providers: list[ToolProvider] = []
        if builtin_services:
            providers.append(
                BuiltinToolProvider(
                    services={
                        **builtin_services,
                        "mcp_tool_gateway": mcp_tool_gateway,
                    }
                )
            )
        providers.append(mcp_tool_gateway)
        return providers

    async def _collect_tools(self) -> tuple[dict[str, ToolDescriptor], dict[str, ToolProvider]]:
        """Aggregate tools from all providers, ensuring no name conflicts and building a mapping of tool names to their owning providers.
        从所有提供程序聚合工具，确保没有名称冲突，并构建工具名称到其所属提供程序的映射。"""
        tools: dict[str, ToolDescriptor] = {}
        owners: dict[str, ToolProvider] = {}
        for provider in self._providers:
            for name, descriptor in (await provider.get_tools()).items():
                if name in tools:
                    raise ValueError(f"duplicate_tool:{name}")
                tools[name] = descriptor
                owners[name] = provider
        return tools, owners

    def _definition_from_descriptor(self, descriptor: ToolDescriptor) -> dict[str, Any]:
        return {
            "type": descriptor.kind,
            "function": {
                "name": descriptor.name,
                "description": descriptor.description,
                "parameters": descriptor.input_schema,
                "strict": self._strict_schema,
            },
        }

    def _matches_allowed_tools(self, tool_name: str, allowed_tools: list[str]) -> bool:
        return any(fnmatchcase(tool_name, pattern) for pattern in allowed_tools)

    def _failed(
        self,
        *,
        call_id: str,
        tool_name: str,
        error_type: str,
        message: str,
        details: list[ErrorDetails] | list[dict[str, Any]] | None = None,
        trace_id: str | None = None,
        tool_trace_id: str | None = None,
        attempt_count: int = 0,
        duration_ms: float = 0.0,
        fallback_reason: str | None = None,
        governance: dict[str, Any] | None = None,
    ) -> ToolExecutionResult:
        payload: dict[str, Any] = {
            "error": {
                "type": error_type,
                "message": message,
            }
        }
        if details is not None:
            payload["error"]["details"] = details
        return ToolExecutionResult(
            call_id=call_id,
            tool_name=tool_name,
            status="failed",
            output=payload,
            error_message=message,
            trace_id=trace_id,
            tool_trace_id=tool_trace_id,
            attempt_count=attempt_count,
            duration_ms=duration_ms,
            fallback_reason=fallback_reason,
            governance=governance,
        )

    async def prepare_arguments(
        self,
        *,
        tool_name: str,
        raw_arguments: dict[str, Any],
        runtime_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        tools, owners = await self._collect_tools()
        if tool_name not in tools:
            raise ValueError(f"unknown_tool:{tool_name}")
        provider = owners[tool_name]
        preparer = getattr(provider, "prepare_arguments", None)
        if not callable(preparer):
            return dict(raw_arguments), []
        return preparer(
            tool_name=tool_name,
            raw_arguments=raw_arguments,
            runtime_context=runtime_context,
        )

    def _policy_for_tool(self, tool_name: str) -> ToolRuntimePolicy:
        metadata_policy: dict[str, Any] = {}
        exact = self._tool_policies.get(tool_name)
        if exact is not None:
            return _merge_policy(exact, metadata_policy)
        for pattern, policy in self._tool_policies.items():
            if pattern != tool_name and fnmatchcase(tool_name, pattern):
                return _merge_policy(policy, metadata_policy)
        return ToolRuntimePolicy()

    def _circuit_error(self, *, tool_name: str, policy: ToolRuntimePolicy) -> str | None:
        state = self._circuit_breakers.get(tool_name)
        if state is None or state.opened_at is None:
            return None
        elapsed = time.monotonic() - state.opened_at
        if elapsed >= policy.circuit_breaker_recovery_seconds:
            self._circuit_breakers[tool_name] = _CircuitState()
            return None
        remaining = max(0.0, policy.circuit_breaker_recovery_seconds - elapsed)
        return f"tool circuit breaker is open for {tool_name}; retry after {remaining:.1f}s"

    def _record_circuit_success(self, tool_name: str) -> None:
        self._circuit_breakers[tool_name] = _CircuitState()

    def _record_circuit_failure(self, tool_name: str, *, policy: ToolRuntimePolicy) -> None:
        state = self._circuit_breakers.setdefault(tool_name, _CircuitState())
        state.failures += 1
        if state.failures >= max(1, policy.circuit_breaker_failures):
            state.opened_at = time.monotonic()

    def _trace_id(self, runtime_context: dict[str, Any] | None) -> str:
        if runtime_context is not None:
            existing = runtime_context.get("tool_trace_id")
            if isinstance(existing, str) and existing:
                return existing
            created = f"trc_{uuid4().hex[:12]}"
            runtime_context["tool_trace_id"] = created
            return created
        return f"trc_{uuid4().hex[:12]}"

    def _consume_budget(
        self,
        *,
        tool_name: str,
        policy: ToolRuntimePolicy,
        runtime_context: dict[str, Any] | None,
    ) -> str | None:
        if runtime_context is None:
            return None
        budget = runtime_context.setdefault("tool_budget", {"tools": {}, "groups": {}})
        if not isinstance(budget, dict):
            runtime_context["tool_budget"] = budget = {"tools": {}, "groups": {}}
        tool_counts = budget.setdefault("tools", {})
        group_counts = budget.setdefault("groups", {})
        if not isinstance(tool_counts, dict) or not isinstance(group_counts, dict):
            runtime_context["tool_budget"] = budget = {"tools": {}, "groups": {}}
            tool_counts = budget["tools"]
            group_counts = budget["groups"]

        current_tool_count = _coerce_count(tool_counts.get(tool_name))
        if policy.max_calls_per_run is not None and current_tool_count >= policy.max_calls_per_run:
            return f"tool budget exceeded for {tool_name}: limit={policy.max_calls_per_run}"

        group = policy.budget_group
        if group:
            group_limit = self._budget_limits.get(group)
            current_group_count = _coerce_count(group_counts.get(group))
            if group_limit is not None and current_group_count >= group_limit:
                return f"tool budget exceeded for group {group}: limit={group_limit}"
            group_counts[group] = current_group_count + 1
        tool_counts[tool_name] = current_tool_count + 1
        return None

    def _budget_snapshot(self, runtime_context: dict[str, Any] | None) -> dict[str, Any] | None:
        if runtime_context is None:
            return None
        budget = runtime_context.get("tool_budget")
        return budget if isinstance(budget, dict) else None

    def _governance_payload(self, *, policy: ToolRuntimePolicy) -> dict[str, Any]:
        return {
            "timeout_seconds": policy.timeout_seconds,
            "max_retries": policy.max_retries,
            "circuit_breaker_failures": policy.circuit_breaker_failures,
            "circuit_breaker_recovery_seconds": policy.circuit_breaker_recovery_seconds,
            "budget_group": policy.budget_group,
            "max_calls_per_run": policy.max_calls_per_run,
        }

    def _elapsed_ms(self, start: float) -> float:
        return round((time.monotonic() - start) * 1000, 2)


def _coerce_count(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _merge_policy(policy: ToolRuntimePolicy, override: dict[str, Any]) -> ToolRuntimePolicy:
    if not override:
        return policy
    return ToolRuntimePolicy(
        timeout_seconds=float(override.get("timeout_seconds", policy.timeout_seconds)),
        max_retries=int(override.get("max_retries", policy.max_retries)),
        circuit_breaker_failures=int(
            override.get("circuit_breaker_failures", policy.circuit_breaker_failures)
        ),
        circuit_breaker_recovery_seconds=float(
            override.get("circuit_breaker_recovery_seconds", policy.circuit_breaker_recovery_seconds)
        ),
        budget_group=override.get("budget_group", policy.budget_group),
        max_calls_per_run=override.get("max_calls_per_run", policy.max_calls_per_run),
    )


def _extract_fallback_reason(output: dict[str, Any]) -> str | None:
    raw = output.get("fallback_reason")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    route = output.get("route")
    if isinstance(route, dict):
        hint = route.get("hint")
        if isinstance(hint, str) and hint.strip():
            return hint.strip()
    return None

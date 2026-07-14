"""Unit tests for environment-driven settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings


def test_settings_reads_llm_and_mcp_dir_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "gpt-test")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "9")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.4")
    monkeypatch.setenv("LLM_MAX_TOKENS", "321")
    monkeypatch.setenv("AGENT_MAX_STEPS", "7")
    monkeypatch.setenv("AGENT_CONTEXT_WINDOW", "18")
    monkeypatch.setenv("AGENT_NODES_DEFINITIONS_DIR", "custom/defs")
    monkeypatch.setenv("AGENT_TOOL_POLICY_FILE", "custom/policy.yaml")
    monkeypatch.setenv("AGENT_SUBAGENT_YAML_OVERLAY_ENABLED", "false")
    monkeypatch.setenv("AGENT_PROVIDER_PROFILES_FILE", "custom/provider_profiles.yaml")
    monkeypatch.setenv("AGENT_PROVIDER_PROFILE", "rule_based")
    monkeypatch.setenv("MCP_DEFAULT_TIMEOUT_SECONDS", "15")
    monkeypatch.setenv("MCP_SERVERS_DIR", "custom/mcp-servers")
    monkeypatch.setenv("AMAP_API_KEY", "amap-key")
    monkeypatch.setenv("AMAP_BASE_URL", "https://restapi.amap.com")
    monkeypatch.setenv("AMAP_TIMEOUT_SECONDS", "6")
    monkeypatch.setenv("ARCADE_DATA_SOURCE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setenv("SUPABASE_TIMEOUT_SECONDS", "11")

    settings = Settings.from_env()

    assert settings.llm_api_key == "test-key"
    assert settings.llm_base_url == "https://api.example.com/v1"
    assert settings.llm_model == "gpt-test"
    assert settings.llm_timeout_seconds == 9
    assert settings.llm_temperature == 0.4
    assert settings.llm_max_tokens == 321
    assert settings.agent_max_steps == 7
    assert settings.agent_context_window == 18
    assert settings.agent_nodes_definitions_dir == Path("custom/defs")
    assert settings.agent_tool_policy_file == Path("custom/policy.yaml")
    assert settings.agent_subagent_yaml_overlay_enabled is False
    assert settings.agent_provider_profiles_file == Path("custom/provider_profiles.yaml")
    assert settings.agent_provider_profile == "rule_based"
    assert settings.mcp_default_timeout_seconds == 15
    assert settings.mcp_servers_dir == Path("custom/mcp-servers")
    assert settings.amap_api_key == "amap-key"
    assert settings.amap_base_url == "https://restapi.amap.com"
    assert settings.amap_timeout_seconds == 6
    assert settings.arcade_data_source == "supabase"
    assert settings.supabase_url == "https://example.supabase.co"
    assert settings.supabase_anon_key == "anon-key"
    assert settings.supabase_service_role_key == "service-key"
    assert settings.supabase_timeout_seconds == 11

def test_settings_does_not_use_openai_env_names(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openai.example.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-openai")

    settings = Settings.from_env()

    assert settings.llm_api_key == ""
    assert settings.llm_base_url == "https://api.openai.com/v1"
    assert settings.llm_model == "gpt-4o-mini"


def test_settings_defaults_include_extended_agent_step_budget(monkeypatch) -> None:
    _ = monkeypatch
    assert Settings.agent_max_steps >= 8


def test_settings_reads_huggingface_runtime_configuration(monkeypatch) -> None:
    monkeypatch.setenv("HF_TOKEN", "hf-private-token")
    monkeypatch.setenv("HUGGINGFACE_CACHE_DIR", "data/test-huggingface")
    monkeypatch.setenv("HF_HUB_OFFLINE", "true")
    monkeypatch.setenv("HUGGINGFACE_DEVICE", "cpu")
    monkeypatch.setenv("HUGGINGFACE_TRUST_REMOTE_CODE", "false")
    monkeypatch.setenv("HUGGINGFACE_REVISION", "model-revision")

    settings = Settings.from_env()

    assert settings.huggingface_token == "hf-private-token"
    assert settings.huggingface_cache_dir.name == "test-huggingface"
    assert settings.huggingface_offline is True
    assert settings.huggingface_device == "cpu"
    assert settings.huggingface_trust_remote_code is False
    assert settings.huggingface_revision == "model-revision"


def test_settings_uses_hf_home_when_project_cache_is_not_set(monkeypatch) -> None:
    # Empty explicit value lets HF_HOME win even when the project .env defines a default.
    monkeypatch.setenv("HUGGINGFACE_CACHE_DIR", "")
    monkeypatch.setenv("HF_HOME", "data/hf-home")

    settings = Settings.from_env()

    assert settings.huggingface_cache_dir.name == "hf-home"


def test_settings_rejects_unknown_arcade_data_source(monkeypatch) -> None:
    monkeypatch.setenv("ARCADE_DATA_SOURCE", "sqlite")

    with pytest.raises(ValueError, match="invalid_arcade_data_source:sqlite"):
        Settings.from_env()


def test_settings_requires_auth_in_production(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_ENABLED", "false")

    with pytest.raises(ValueError, match="production_requires_auth_enabled"):
        Settings.from_env()


def test_settings_rejects_incomplete_auth_configuration(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("JWT_ISSUER", "")
    monkeypatch.setenv("JWT_AUDIENCE", "")
    monkeypatch.setenv("JWT_ALGORITHMS", "")
    monkeypatch.setenv("JWT_JWKS_URL", "")
    monkeypatch.setenv("JWT_SECRET", "")
    monkeypatch.setenv("SUPABASE_URL", "")

    with pytest.raises(ValueError, match="incomplete_auth_configuration") as exc_info:
        Settings.from_env()

    message = str(exc_info.value)
    assert "JWT_ISSUER" in message
    assert "JWT_AUDIENCE" in message
    assert "JWT_ALGORITHMS" in message
    assert "JWT_SECRET_OR_JWT_JWKS_URL" in message

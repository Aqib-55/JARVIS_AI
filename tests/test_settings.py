"""Tests for settings validation — Ollama local-only configuration."""

from config.settings import Settings


class TestSettingsValidation:

    def test_valid_ollama_config(self, monkeypatch):
        """Standard valid local configuration should produce no errors."""
        monkeypatch.setenv("AI_PROVIDER", "ollama")
        monkeypatch.setenv("LOCAL_AI_ONLY", "true")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:4b")
        s = Settings()
        errors = s.validate()
        assert errors == [], f"Unexpected validation errors: {errors}"

    def test_invalid_provider(self, monkeypatch):
        """Non-ollama provider should produce a validation error."""
        monkeypatch.setenv("AI_PROVIDER", "gemini")
        monkeypatch.setenv("LOCAL_AI_ONLY", "true")
        monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:4b")
        s = Settings()
        errors = s.validate()
        assert any("AI_PROVIDER" in e for e in errors)

    def test_external_url_blocked_in_local_only(self, monkeypatch):
        """External Ollama URL must be rejected when LOCAL_AI_ONLY=true."""
        monkeypatch.setenv("AI_PROVIDER", "ollama")
        monkeypatch.setenv("LOCAL_AI_ONLY", "true")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.1.100:11434")
        monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:4b")
        s = Settings()
        errors = s.validate()
        assert any("non-local" in e or "loopback" in e for e in errors)

    def test_localhost_allowed(self, monkeypatch):
        """localhost is a valid loopback address."""
        monkeypatch.setenv("AI_PROVIDER", "ollama")
        monkeypatch.setenv("LOCAL_AI_ONLY", "true")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:4b")
        s = Settings()
        errors = s.validate()
        assert errors == [], f"Unexpected errors: {errors}"

    def test_missing_model(self, monkeypatch):
        """Empty OLLAMA_MODEL should produce a validation error."""
        monkeypatch.setenv("AI_PROVIDER", "ollama")
        monkeypatch.setenv("LOCAL_AI_ONLY", "true")
        monkeypatch.setenv("OLLAMA_MODEL", "")
        s = Settings()
        errors = s.validate()
        assert any("OLLAMA_MODEL" in e for e in errors)

    def test_invalid_history_limit(self, monkeypatch):
        """Zero conversation history limit should produce a validation error."""
        monkeypatch.setenv("AI_PROVIDER", "ollama")
        monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:4b")
        monkeypatch.setenv("MAX_CONVERSATION_HISTORY", "0")
        s = Settings()
        errors = s.validate()
        assert any("MAX_CONVERSATION_HISTORY" in e for e in errors)

    def test_local_only_flag_true(self, monkeypatch):
        """LOCAL_AI_ONLY=true should be parsed correctly."""
        monkeypatch.setenv("LOCAL_AI_ONLY", "true")
        s = Settings()
        assert s.LOCAL_AI_ONLY is True

    def test_local_only_flag_false(self, monkeypatch):
        """LOCAL_AI_ONLY=false should be parsed correctly."""
        monkeypatch.setenv("LOCAL_AI_ONLY", "false")
        s = Settings()
        assert s.LOCAL_AI_ONLY is False

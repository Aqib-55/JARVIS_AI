"""Tests for settings validation and environment configuration."""

from unittest.mock import patch

from config.settings import Settings


class TestSettingsValidation:

    def test_missing_api_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "")
        s = Settings()
        errors = s.validate()
        assert any("GEMINI_API_KEY is not set" in e for e in errors)

    def test_placeholder_api_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "your_gemini_api_key_here")
        s = Settings()
        errors = s.validate()
        assert any("placeholder value" in e for e in errors)

    def test_short_api_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "abc12")
        s = Settings()
        errors = s.validate()
        assert any("too short" in e for e in errors)

    def test_valid_api_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFakeKeyForTesting123456789")
        s = Settings()
        errors = s.validate()
        assert len(errors) == 0

    def test_invalid_history_limit(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFakeKeyForTesting123456789")
        monkeypatch.setenv("MAX_CONVERSATION_HISTORY", "0")
        s = Settings()
        errors = s.validate()
        assert any("MAX_CONVERSATION_HISTORY" in e for e in errors)

"""Tests for the main() entry point."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from main import main


class TestMainEntry:
    def test_missing_all_vars(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "SUPABASE_URL" in captured.out
        assert "SUPABASE_SERVICE_ROLE_KEY" in captured.out
        assert "OPENROUTER_API_KEY" in captured.out

    def test_missing_one_var(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "key")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "OPENROUTER_API_KEY" in captured.out
        assert "SUPABASE_URL" not in captured.out

    @patch("main.VisibilityReviewApp")
    def test_launches_app(
        self,
        mock_app_cls: Mock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "key")
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
        main()
        mock_app_cls.assert_called_once()
        mock_app_cls.return_value.run.assert_called_once()

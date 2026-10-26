"""The opt-in checker must isolate data and never leak provider errors."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from culturebridge.config import get_settings


@pytest.fixture
def checker():
    path = Path(__file__).resolve().parents[1] / "scripts/check_external_connections.py"
    spec = importlib.util.spec_from_file_location("external_connection_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("failure", [False, True])
def test_isolated_report_and_settings_restored(checker, monkeypatch, tmp_path, failure):
    monkeypatch.chdir(tmp_path)
    settings = get_settings()
    original = settings.model_copy(deep=True)

    class Client:
        def __init__(self, app):
            self.count = 0

        def __enter__(self):
            assert settings.db_path == tmp_path / "outputs/check.db"
            assert not settings.gemini_enabled
            assert not settings.maintenance_enabled
            return self

        def __exit__(self, *args):
            pass

        def get(self, path, params):
            self.count += 1
            if failure:
                raise RuntimeError("private-provider-error-and-key")
            payload = {
                "items": [1],
                "records": [1],
                "content": "source",
                "projected_x": 1,
                "cached": self.count in (3, 6),
                "stale": False,
            }
            return type("Response", (), {"status_code": 200, "json": lambda _: payload})()

    monkeypatch.setattr(checker, "TestClient", Client)
    monkeypatch.setattr(checker, "search_history", lambda _: ([1], None))
    monkeypatch.setattr(sys, "argv", ["check", "--live", "--output", "outputs/check.json"])
    assert checker.main() == int(failure)
    raw = (tmp_path / "outputs/check.json").read_text(encoding="utf-8")
    report = json.loads(raw)
    assert len(report["checks"]) == 9
    assert report["gemini_calls"] == 0
    assert report["dictionary"] == "deferred_by_user"
    assert "private-provider-error" not in raw
    assert settings == original


@pytest.mark.parametrize("target", ["report.json", "outputs/existing.json"])
def test_rejects_unsafe_or_existing_report(checker, monkeypatch, tmp_path, target):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs/existing.json").touch()
    monkeypatch.setattr(sys, "argv", ["check", "--live", "--output", target])
    with pytest.raises(SystemExit):
        checker.main()

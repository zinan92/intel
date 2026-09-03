"""Codex CLI fallback isolation and failure tests."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from llm.codex import CodexCLIClient, CodexCLIError


def test_codex_client_uses_isolated_read_only_stdin(monkeypatch):
    from llm import codex as mod

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text('{"results": []}', encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(mod, "_resolve_executable", lambda: "/opt/homebrew/bin/codex")
    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    result = CodexCLIClient().complete(
        "score this batch",
        system_prompt="Return the scoring contract",
        json_mode=True,
    )

    command = captured["command"]
    assert result == '{"results": []}'
    assert command[-1] == "-"
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in command
    assert "--ignore-user-config" in command
    assert "score this batch" in captured["kwargs"]["input"]
    assert "Return valid JSON only" in captured["kwargs"]["input"]


def test_codex_client_raises_on_nonzero_exit(monkeypatch):
    from llm import codex as mod

    monkeypatch.setattr(mod, "_resolve_executable", lambda: "/opt/homebrew/bin/codex")
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=2, stdout=""),
    )

    with pytest.raises(CodexCLIError, match="exit_2"):
        CodexCLIClient().complete("prompt")

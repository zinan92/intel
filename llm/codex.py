"""Isolated Codex CLI completion client for Finance Newsletter fallbacks."""

from __future__ import annotations

import json
from datetime import datetime, timezone
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


USAGE_LOG = Path.home() / "park-data" / "llm-usage" / "finance-daily.jsonl"


def _log_codex_usage(stdout: str) -> None:
    """Parse the '--json' event stream's turn.completed usage line. The client
    already asks for --json and reads --output-last-message for the answer;
    the usage line inside that same stdout was simply never looked at."""
    usage = None
    for line in reversed((stdout or "").splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "turn.completed":
            usage = event.get("usage")
            break
    if not isinstance(usage, dict):
        return
    try:
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with USAGE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "provider": "codex",
                "input_tokens": usage.get("input_tokens"),
                "cached_input_tokens": usage.get("cached_input_tokens"),
                "output_tokens": usage.get("output_tokens"),
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass


class CodexCLIError(RuntimeError):
    """Raised when the local Codex CLI cannot return usable content."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Codex CLI completion failed: {reason}")
        self.reason = reason


def _resolve_executable() -> str:
    candidates = (
        os.getenv("PARK_CODEX_CLI", "").strip(),
        shutil.which("codex") or "",
        "/opt/homebrew/bin/codex",
        "/usr/local/bin/codex",
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    return "codex"


def _text_from_jsonl(stdout: str) -> str | None:
    for line in reversed((stdout or "").splitlines()):
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        for key in ("text", "content", "output", "message"):
            value = event.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                nested = value.get("content") or value.get("text")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
    return None


class CodexCLIClient:
    """Run one non-interactive completion without tools or workspace access."""

    provider = "codex-cli"

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        json_mode: bool = False,
        timeout: float = 300,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> str:
        del max_tokens, temperature
        instructions = [
            "Use only the supplied prompt. Do not inspect files, browse, call tools, or modify state.",
        ]
        if system_prompt:
            instructions.append(system_prompt)
        if json_mode:
            instructions.append("Return valid JSON only, with no markdown fences or surrounding prose.")
        instructions.append(prompt)
        stdin_payload = "\n\n".join(instructions)

        with tempfile.TemporaryDirectory(prefix="park-intel-codex-") as directory:
            root = Path(directory)
            output_path = root / "codex-output.txt"
            command = [
                _resolve_executable(),
                "exec",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--ignore-user-config",
                "--color",
                "never",
                "--disable",
                "shell_tool",
                "--disable",
                "browser_use",
                "--disable",
                "browser_use_external",
                "--disable",
                "computer_use",
                "--disable",
                "apps",
                "--disable",
                "unified_exec",
                "--json",
                "--output-last-message",
                str(output_path),
                "-C",
                str(root),
                "-",
            ]
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(root),
                    input=stdin_payload,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise CodexCLIError("timeout") from exc
            except OSError as exc:
                raise CodexCLIError("executable_unavailable") from exc

            if completed.returncode != 0:
                raise CodexCLIError(f"exit_{completed.returncode}")
            content = None
            if output_path.is_file():
                content = output_path.read_text(encoding="utf-8").strip() or None
            content = content or _text_from_jsonl(completed.stdout)
            _log_codex_usage(completed.stdout)
            if not content:
                raise CodexCLIError("empty_response")
            return content

"""Minimal DeepSeek Chat Completions client with file-based credentials."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

DEFAULT_KEY_FILE = Path("/Users/wendy/park-hands/_secrets/deepseek-key")
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


class DeepSeekError(RuntimeError):
    """Raised when a DeepSeek request cannot produce usable content."""


def _read_api_key(path: Path) -> str:
    try:
        api_key = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise DeepSeekError(f"DeepSeek credential file is unavailable: {path}") from exc
    if not api_key:
        raise DeepSeekError(f"DeepSeek credential file is empty: {path}")
    return api_key


class DeepSeekClient:
    """Synchronous client used by scheduler jobs and maintenance scripts."""

    def __init__(
        self,
        *,
        key_file: Path | str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        configured_key_file = key_file or os.getenv("DEEPSEEK_KEY_FILE") or DEFAULT_KEY_FILE
        self.key_file = Path(configured_key_file)
        self.base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.getenv("DEEPSEEK_MODEL") or DEFAULT_MODEL

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        json_mode: bool = False,
        timeout: float = 120,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "thinking": {"type": "disabled"},
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {_read_api_key(self.key_file)}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except requests.Timeout as exc:
            raise DeepSeekError("DeepSeek request timed out") from exc
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            raise DeepSeekError("DeepSeek request failed or returned an invalid response") from exc

        if not isinstance(content, str) or not content.strip():
            raise DeepSeekError("DeepSeek returned empty content")
        return content.strip()

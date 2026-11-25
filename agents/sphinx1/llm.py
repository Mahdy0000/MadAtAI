"""LLM backends behind one interface, so the backend is a config switch.

    chat(system, user, image_jpeg=None, json_mode=False) -> str

- OllamaLLM: local models via the Ollama HTTP API (vision models accept images).
- OpenAILLM: any OpenAI-compatible /chat/completions endpoint (OpenAI, vLLM, LM Studio, ...).
- MockLLM: offline, rule-based. Lets the whole system run with no model and no network.

Only the standard library is used (urllib).
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.request
from abc import ABC, abstractmethod

from .config import LLMCfg


class LLM(ABC):
    @abstractmethod
    def chat(self, system: str, user: str, image_jpeg: bytes | None = None, json_mode: bool = False) -> str: ...


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", **headers}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


class OllamaLLM(LLM):
    def __init__(self, cfg: LLMCfg):
        self.base = (cfg.base_url or "http://localhost:11434").rstrip("/")
        self.model, self.timeout = cfg.model, cfg.timeout_s

    def chat(self, system, user, image_jpeg=None, json_mode=False):
        msg = {"role": "user", "content": user}
        if image_jpeg:
            msg["images"] = [base64.b64encode(image_jpeg).decode()]
        payload = {"model": self.model, "stream": False, "messages": [{"role": "system", "content": system}, msg]}
        if json_mode:
            payload["format"] = "json"
        return _post_json(f"{self.base}/api/chat", payload, {}, self.timeout)["message"]["content"]


class OpenAILLM(LLM):
    def __init__(self, cfg: LLMCfg):
        self.base = (cfg.base_url or "https://api.openai.com/v1").rstrip("/")
        self.model, self.timeout = cfg.model, cfg.timeout_s
        self.key = os.environ.get(cfg.api_key_env, "")

    def chat(self, system, user, image_jpeg=None, json_mode=False):
        content: list | str = user
        if image_jpeg:
            b64 = base64.b64encode(image_jpeg).decode()
            content = [
                {"type": "text", "text": user},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]
        payload = {"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        return _post_json(f"{self.base}/chat/completions", payload, headers, self.timeout)["choices"][0]["message"]["content"]


class MockLLM(LLM):
    """Offline stand-in. Returns '{}' so callers use their own rule-based fallbacks."""

    def chat(self, system, user, image_jpeg=None, json_mode=False):
        return "{}"


def make_llm(cfg: LLMCfg) -> LLM:
    table = {"mock": MockLLM, "ollama": OllamaLLM, "openai": OpenAILLM}
    if cfg.provider not in table:
        raise ValueError(f"unknown llm provider {cfg.provider!r}; choose one of {sorted(table)}")
    return table[cfg.provider](cfg) if cfg.provider != "mock" else MockLLM()


def parse_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply. Returns {} if there is none."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        out = json.loads(m.group(0))
        return out if isinstance(out, dict) else {}
    except json.JSONDecodeError:
        return {}

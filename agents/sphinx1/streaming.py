"""Token streaming from Ollama and OpenAI-compatible servers. Standard library only.

stream_chat(cfg, system, user, image_jpeg, max_tokens) yields text pieces as the model produces them.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request
from typing import Iterator

from .config import LLMCfg


def stream_chat(cfg: LLMCfg, system: str, user: str, image_jpeg: bytes | None = None, max_tokens: int = 80) -> Iterator[str]:
    if cfg.provider == "ollama":
        yield from _ollama(cfg, system, user, image_jpeg, max_tokens)
    elif cfg.provider == "openai":
        yield from _openai(cfg, system, user, image_jpeg, max_tokens)
    else:
        raise ValueError(f"provider {cfg.provider!r} cannot stream")


def _ollama(cfg, system, user, image, max_tokens):
    base = (cfg.base_url or "http://localhost:11434").rstrip("/")
    msg = {"role": "user", "content": user}
    if image:
        msg["images"] = [base64.b64encode(image).decode()]
    payload = {
        "model": cfg.model, "stream": True, "keep_alive": "30m",
        "messages": [{"role": "system", "content": system}, msg],
        "options": {"num_predict": max_tokens, "temperature": 0.7},
    }
    req = urllib.request.Request(f"{base}/api/chat", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=cfg.timeout_s) as resp:
        for line in resp:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("error"):
                raise RuntimeError(obj["error"])
            piece = obj.get("message", {}).get("content", "")
            if piece:
                yield piece
            if obj.get("done"):
                break


def _openai(cfg, system, user, image, max_tokens):
    base = (cfg.base_url or "https://api.openai.com/v1").rstrip("/")
    content = user
    if image:
        b64 = base64.b64encode(image).decode()
        content = [{"type": "text", "text": user}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]
    payload = {"model": cfg.model, "stream": True, "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
    headers = {"Content-Type": "application/json"}
    key = os.environ.get(cfg.api_key_env, "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(f"{base}/chat/completions", data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=cfg.timeout_s) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if body == "[DONE]":
                break
            choices = json.loads(body).get("choices") or [{}]
            piece = choices[0].get("delta", {}).get("content") or ""
            if piece:
                yield piece

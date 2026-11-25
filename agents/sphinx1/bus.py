"""A tiny in-process message bus. Agents never call each other: they send Messages.

Every message is logged, so a run is a readable transcript of the agents negotiating.
"""
from __future__ import annotations

import itertools
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable

_ids = itertools.count(1)


@dataclass
class Message:
    sender: str
    to: str                      # agent name, or "all"
    kind: str                    # goal, observation, proposal, approve, veto, done, ...
    data: dict[str, Any] = field(default_factory=dict)
    id: int = field(default_factory=lambda: next(_ids))
    ts: float = field(default_factory=time.time)


class Bus:
    def __init__(self, on_message: Callable[[Message], None] | None = None):
        self.history: list[Message] = []
        self._inbox: dict[str, deque[Message]] = defaultdict(deque)
        self._agents: set[str] = set()
        self._on_message = on_message

    def register(self, name: str) -> None:
        self._agents.add(name)

    def send(self, sender: str, to: str, kind: str, **data: Any) -> Message:
        msg = Message(sender, to, kind, data)
        self.history.append(msg)
        targets = [a for a in self._agents if a != sender] if to == "all" else [to]
        for t in targets:
            self._inbox[t].append(msg)
        if self._on_message:
            self._on_message(msg)
        return msg

    def stream(self, sender: str, to: str, kind: str, chunks, on_chunk: Callable[[str], None] | None = None, **data: Any) -> Message:
        """Send a message whose text arrives piece by piece. on_chunk sees each piece as it is produced;
        the complete message (data["text"]) is delivered to the recipients once the stream ends."""
        parts: list[str] = []
        try:
            for c in chunks:
                parts.append(c)
                if on_chunk:
                    on_chunk(c)
        finally:
            msg = self.send(sender, to, kind, text="".join(parts), **data)
        return msg

    def receive(self, name: str, kind: str | None = None) -> list[Message]:
        """Drain and return the agent's inbox (optionally only one kind; others stay queued)."""
        box = self._inbox[name]
        taken, kept = [], deque()
        while box:
            m = box.popleft()
            (taken if kind is None or m.kind == kind else kept).append(m)
        self._inbox[name] = kept
        return taken

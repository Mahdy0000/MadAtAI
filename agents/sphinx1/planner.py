"""Planner agent: understands the task (Arabic or English), then supervises the navigator.

1. decompose(): LLM turns the task into a structured goal. If the LLM is unavailable or
   returns junk, a rule-based parser (small Arabic/English vocabulary) takes over.
2. review(): every tick it approves or vetoes the navigator's proposal. It stops endless
   spinning (forces exploring), and demands repeated arrival proposals before it declares success.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .bus import Bus
from .config import PlannerCfg
from .llm import LLM, parse_json

SYSTEM = (
    "You plan tasks for a small wheeled robot that can look through a camera, drive, and find objects. "
    "The user gives a task in Arabic or English. Reply with JSON only: "
    '{"language": "ar"|"en", "target_en": "<short English description of the object, e.g. red bottle>", '
    '"target_original": "<the object as the user wrote it>", '
    '"subgoals": ["search for the object", "approach it", "stop close to it"]}'
)

_AR = re.compile(r"[\u0600-\u06FF]")
_DIACRITICS = re.compile(r"[\u064B-\u0652\u0640]")

_EN_STOP = {"find", "bring", "get", "fetch", "go", "to", "me", "the", "a", "an", "please", "look", "for", "and", "reach", "locate"}
_AR_STOP = {"هات", "هاتلي", "جيب", "جيبلي", "لي", "ليا", "دور", "دورلي", "على", "علي", "عن", "ابحث", "الي", "إلى", "روح", "اوصل", "ممكن", "من", "فضلك", "لو", "سمحت"}
_AR_WORDS = {
    "زجاجة": "bottle", "قزازة": "bottle", "كوب": "cup", "كوباية": "cup", "كورة": "ball", "كرة": "ball",
    "علبة": "box", "صندوق": "box", "كتاب": "book", "موبايل": "phone", "هاتف": "phone", "قلم": "pen",
    "شنطة": "bag", "حقيبة": "bag", "مفتاح": "key", "مفاتيح": "keys", "كرسي": "chair",
}
_AR_COLORS = {
    "احمر": "red", "حمرا": "red", "حمراء": "red", "ازرق": "blue", "زرقا": "blue", "زرقاء": "blue",
    "اخضر": "green", "خضرا": "green", "خضراء": "green", "اصفر": "yellow", "صفرا": "yellow", "صفراء": "yellow",
    "ابيض": "white", "بيضا": "white", "بيضاء": "white", "اسود": "black", "سودا": "black", "سوداء": "black",
}
_ALEF = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})


def _norm(w: str) -> str:
    return _DIACRITICS.sub("", w).translate(_ALEF)


def rule_based_goal(task: str) -> dict:
    """Fallback parser. Understands the verbs/objects/colors in the tables above; everything else is kept as-is."""
    ar = bool(_AR.search(task))
    words = re.findall(r"[\w\u0600-\u06FF]+", task.lower())
    colors, nouns, rest = [], [], []
    for w in words:
        if ar:
            n = _norm(w)
            if n in {_norm(s) for s in _AR_STOP}:
                continue
            base = n[2:] if n.startswith("ال") and len(n) > 3 else n
            norm_words = {_norm(k): v for k, v in _AR_WORDS.items()}
            norm_colors = {_norm(k): v for k, v in _AR_COLORS.items()}
            if base in norm_colors:
                colors.append(norm_colors[base])
            elif base in norm_words:
                nouns.append(norm_words[base])
            else:
                rest.append(w)
        elif w not in _EN_STOP:
            (colors if w in set(_AR_COLORS.values()) else nouns).append(w)
    target_en = " ".join(colors + nouns) or " ".join(rest) or task.strip()
    return {"language": "ar" if ar else "en", "target_en": target_en, "target_original": " ".join(w for w in words if w not in _EN_STOP) if not ar else (" ".join(rest) or task.strip()),
            "subgoals": ["search for the object", "approach it", "stop close to it"]}


@dataclass
class PlannerState:
    search_turns: int = 0
    explore_left: int = 0
    arrive_streak: int = 0
    done: bool = False
    goal: dict = field(default_factory=dict)


class PlannerAgent:
    name = "planner"

    def __init__(self, bus: Bus, llm: LLM, cfg: PlannerCfg):
        self.bus, self.llm, self.cfg = bus, llm, cfg
        self.state = PlannerState()
        self.last_obs: dict = {}
        bus.register(self.name)

    def decompose(self, task: str) -> dict:
        goal: dict = {}
        try:
            goal = parse_json(self.llm.chat(SYSTEM, task, json_mode=True))
        except Exception as e:  # network down, model missing, bad reply: fall back, do not crash
            self.bus.send(self.name, "all", "note", text=f"LLM unavailable ({type(e).__name__}); using rule-based parser")
        if not str(goal.get("target_en", "")).strip():
            goal = rule_based_goal(task)
        goal["task"] = task
        self.state.goal = goal
        self.bus.send(self.name, "all", "goal", **goal)
        return goal

    def review(self) -> dict:
        """Read the navigator's proposal and answer approve / veto."""
        for m in self.bus.receive(self.name, "observation"):
            self.last_obs = m.data
        props = self.bus.receive(self.name, "proposal")
        if not props:
            return {}
        p, s, c = props[-1].data, self.state, self.cfg
        action = p["action"]
        s.arrive_streak = s.arrive_streak + 1 if action == "arrived" else 0
        s.search_turns = s.search_turns + 1 if action == "spin" else (0 if action in ("approach", "turn") else s.search_turns)

        if action == "arrived":
            if s.arrive_streak >= c.confirm_arrivals and self.last_obs.get("seen"):
                s.done = True
                self.bus.send(self.name, "all", "done", reason="target reached", target=s.goal.get("target_en"))
                return self._approve()
            return self._veto("hold", f"arrival {s.arrive_streak}/{c.confirm_arrivals}: look once more before declaring success")
        if action == "spin":
            if s.explore_left > 0:
                s.explore_left -= 1
                return self._veto("explore", "exploring instead of spinning")
            if s.search_turns > c.max_search_turns:
                s.search_turns, s.explore_left = 0, 20
                return self._veto("explore", f"scanned {c.max_search_turns} turns without finding it, moving to a new spot")
        return self._approve()

    def _approve(self) -> dict:
        self.bus.send(self.name, "navigator", "approve")
        return {"approved": True}

    def _veto(self, replacement: str, reason: str) -> dict:
        self.bus.send(self.name, "navigator", "veto", replacement=replacement, reason=reason)
        return {"approved": False, "replacement": replacement}

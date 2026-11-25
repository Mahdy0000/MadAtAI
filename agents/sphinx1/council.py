"""The council: four agents (planner, vision, navigator, safety), each on its own model, talk to each other live.

A round is a short conversation. Each agent sees what the others already said in this round and replies in
one or two sentences, streamed token by token over the bus. The robot's control loop stays deterministic:
the council explains and challenges what the agents are doing, it never sends motor commands by itself.
If a model is unreachable the agent falls back to a scripted line (marked "fallback") so the demo never stalls.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterator

from .bus import Bus
from .config import CouncilCfg, LLMCfg
from .streaming import stream_chat

ORDER = ["planner", "vision", "navigator", "safety"]

ROLES = {
    "planner": "You are PLANNER. You understand the task, set the plan and make the final call on what the team does next.",
    "vision": "You are VISION. You only report what the camera sees about the target: seen or not, left/right/ahead, near or far.",
    "navigator": "You are NAVIGATOR. You propose the next move for the wheels and say why, reacting to what vision reported.",
    "safety": "You are SAFETY. You check the proposed move against the ultrasonic distance and stalls, and approve or object.",
}

ASKS = {
    "plan": "A new task just arrived. State the plan in one sentence." ,
    "sighted": "The target just came into view.",
    "obstacle": "The ultrasonic sensor reports an obstacle.",
    "veto": "The planner just vetoed the navigator's proposal.",
    "arrived": "The robot believes it reached the target.",
    "periodic": "Quick status check mid-run.",
    "done": "The task is finished.",
}


@dataclass
class Turn:
    agent: str
    model: str
    text: str
    fallback: bool


def _dir(b: float, ar: bool) -> str:
    if b < -0.15:
        return "على الشمال" if ar else "to the left"
    if b > 0.15:
        return "على اليمين" if ar else "to the right"
    return "قدامي" if ar else "straight ahead"


def scripted(agent: str, topic: str, f: dict, ar: bool) -> str:
    """Offline lines built from the real facts. Used with provider = mock, or when a model is unreachable."""
    t = f.get("target", "target")
    if ar and f.get("target_ar"):
        t = f["target_ar"]
    d = f.get("distance", "?")
    where = _dir(float(f.get("bearing", 0.0)), ar)
    act = f.get("action", "spin")
    why = f.get("why", "")
    if topic == "plan":
        return {
            "planner": f"المهمة: ألاقي {t} وأقف جنبه. هندور الأول وبعدين نقرّب." if ar else f"Task: find the {t} and stop next to it. Scan first, then approach.",
            "vision": f"جاهز. هدوّر على {t} في كل فريم وأقولكم الاتجاه." if ar else f"Ready. I will look for the {t} in every frame and report its direction.",
            "navigator": "هلف في مكاني لحد ما الرؤية تلاقي الهدف، وبعدين أتحرك ناحيته." if ar else "I will spin in place until vision finds it, then drive toward it.",
            "safety": "هراقب الحساس: أي عائق أقرب من 18 سم، أوقف وأطلب نلف." if ar else "I watch the ultrasonic sensor: anything closer than 18 cm and I ask for a stop and a turn.",
        }[agent]
    if topic == "veto":
        rule = f.get("planner_ruling", "vetoed")
        pl = {"ar": f"رفضت اقتراح الملاح ({rule}). لازم نتأكد قبل ما نكمل.", "en": f"I overruled the navigator ({rule}). We check again before continuing."}
        if agent == "planner":
            return pl["ar" if ar else "en"]
    if ar:
        seen = f"شايف الهدف ({t}) {where}" if f.get("seen") else f"مش شايف {t} دلوقتي"
        return {
            "planner": {"plan": f"المهمة: ألاقي {t} وأقف جنبه. هندور الأول وبعدين نقرّب.",
                        "arrived": f"لو الوصول اتأكد مرتين، أعلن إن {t} اتلاقى."}.get(topic, f"نكمل: الهدف {t}، والخطة سليمة."),
            "vision": seen + ".",
            "navigator": f"اقتراحي: {act}. السبب: {why}.",
            "safety": (f"المسافة {d} سم. " if d != "no echo" else "مفيش عائق قدامنا. ") + ("اعتراض: خلّينا نبعد عن العائق." if topic == "obstacle" else "الحركة آمنة، وأنا موافق."),
        }[agent]
    seen = f"I see the {t} {where}" if f.get("seen") else f"I do not see the {t} right now"
    return {
        "planner": {"plan": f"Task: find the {t} and stop next to it. Scan first, then approach.",
                    "arrived": f"If arrival is confirmed twice, I declare the {t} found."}.get(topic, f"Keep going: target is the {t}, plan unchanged."),
        "vision": seen + ".",
        "navigator": f"My proposal: {act}. Reason: {why}.",
        "safety": (f"Distance is {d} cm. " if d != "no echo" else "No obstacle in range. ") + ("Objection: back away from the obstacle first." if topic == "obstacle" else "Move is safe, I approve."),
    }[agent]


class Council:
    def __init__(self, bus: Bus, cfg: CouncilCfg, sinks: list, step_timeout: float | None = None):
        self.bus, self.cfg, self.sinks = bus, cfg, sinks
        self.rounds = 0
        for a in ORDER:
            bus.register(f"{a}")

    def model_for(self, agent: str) -> str:
        return getattr(self.cfg, f"{agent}_model") if self.cfg.provider != "mock" else "scripted"

    def _llm_cfg(self, agent: str) -> LLMCfg:
        c = self.cfg
        return LLMCfg(provider=c.provider, model=self.model_for(agent), base_url=c.base_url, api_key_env=c.api_key_env, timeout_s=c.timeout_s)

    def _emit(self, name: str, *args) -> None:
        for s in self.sinks:
            getattr(s, name)(*args)

    def _system(self, agent: str, ar: bool) -> str:
        lang = "Reply in Arabic (simple, clear)." if ar else "Reply in English."
        return (f"{ROLES[agent]} You are in a live discussion with the other agents of a small wheeled robot that searches for an object. "
                f"Speak in first person, at most {self.cfg.max_words} words, one or two sentences, no lists, no markdown. "
                f"Use only the facts you are given; never invent numbers. {lang}")

    def _user(self, topic: str, facts: dict, said: list[Turn], agent: str) -> str:
        lines = [f"Situation: {ASKS[topic]}", "Facts: " + "; ".join(f"{k}={v}" for k, v in facts.items() if k != "frame")]
        if said:
            lines.append("So far in this discussion:")
            lines += [f"{t.agent}: {t.text}" for t in said]
        lines.append(f"Now it is your turn, {agent}. Answer the others directly.")
        return "\n".join(lines)

    def _speak(self, agent: str, topic: str, facts: dict, said: list[Turn], ar: bool) -> Turn:
        model = self.model_for(agent)
        self._emit("start", agent, model)
        pieces: list[str] = []
        fallback = False

        def on_chunk(c: str) -> None:
            pieces.append(c)
            self._emit("token", agent, c)

        def chunks() -> Iterator[str]:
            nonlocal fallback
            if self.cfg.provider != "mock":
                try:
                    image = facts.get("frame") if agent == "vision" else None
                    yield from stream_chat(self._llm_cfg(agent), self._system(agent, ar), self._user(topic, facts, said, agent), image,
                                           max_tokens=int(self.cfg.max_words * 3.2) + 20)
                    return
                except Exception as e:  # model missing, server down, timeout: say so, then use the scripted line
                    if pieces:
                        return
                    fallback = True
                    self._emit("note", f"{agent}: model '{model}' unavailable ({type(e).__name__}), using fallback line")
            text = scripted(agent, topic, facts, ar)
            for w in text.split(" "):
                time.sleep(self.cfg.token_delay_s)
                yield w + " "

        msg = self.bus.stream(agent, "all", "say", chunks(), on_chunk, topic=topic, model=model)
        text = msg.data["text"].strip()
        self._emit("end", agent, text, fallback)
        return Turn(agent, model, text, fallback)

    def discuss(self, topic: str, facts: dict, ar: bool = False) -> list[Turn]:
        self.rounds += 1
        self._emit("round", topic, self.rounds)
        said: list[Turn] = []
        for agent in ORDER:
            said.append(self._speak(agent, topic, facts, said, ar))
        return said

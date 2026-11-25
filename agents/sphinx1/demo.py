"""Live demo: four agents on four models talk to each other, streamed, while the robot (or simulator) runs.

    python -m sphinx1.demo --task "find the red bottle"            # terminal, scripted voices (no model needed)
    python -m sphinx1.demo --council ollama --web                   # real Ollama models + browser view for the judges
    python -m sphinx1.demo --council ollama --web --robot http --url http://<robot-ip> --vision vlm --llm ollama
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser

from .bus import Bus
from .config import Config, load_config
from .council import ORDER, Council
from .llm import make_llm
from .navigator import NavigatorAgent
from .planner import PlannerAgent
from .runner import RunResult, make_robot
from .vision import VisionAgent, make_detector

COLORS = {"planner": "\033[96m", "vision": "\033[92m", "navigator": "\033[93m", "safety": "\033[91m"}
RESET, DIM = "\033[0m", "\033[2m"


class ConsoleSink:
    def __init__(self):
        self._open = None

    def round(self, topic, n):
        print(f"\n{DIM}--- round {n}: {topic} ---{RESET}", flush=True)

    def start(self, agent, model):
        print(f"{COLORS[agent]}{agent:>9} ({model}){RESET}: ", end="", flush=True)

    def token(self, agent, text):
        print(text, end="", flush=True)

    def end(self, agent, text, fallback):
        print(f"{DIM} [fallback]{RESET}" if fallback else "", flush=True)

    def note(self, text):
        print(f"{DIM}{text}{RESET}", flush=True)

    def event(self, text):
        print(f"{DIM}{text}{RESET}", flush=True)


def preflight(cfg: Config, sinks: list) -> bool:
    """With real models: check Ollama is up and the four models are pulled; say exactly what to fix. Never blocks the demo."""
    c = cfg.council
    if c.provider != "ollama":
        return True
    from .streaming import missing_models, ollama_models
    try:
        installed = ollama_models(c.base_url)
    except OSError as e:
        for s in sinks:
            s.note(f"Ollama is not reachable ({type(e).__name__}). Start it (open the Ollama app), or agents will use scripted fallback lines.")
        return False
    wanted = [c.planner_model, c.vision_model, c.navigator_model, c.safety_model]
    miss = missing_models(wanted, installed)
    for m in miss:
        for s in sinks:
            s.note(f"model not installed: run  ollama pull {m}   (that agent will use a fallback line until then)")
    if not miss:
        for s in sinks:
            s.note("preflight ok: Ollama is up and all four models are installed")
    return not miss


def run_demo(task: str, cfg: Config, sinks: list, seed: int = 1) -> RunResult:
    def emit(name, *a):
        for s in sinks:
            getattr(s, name)(*a)

    preflight(cfg, sinks)
    bus = Bus()
    robot = make_robot(cfg, seed)
    llm = make_llm(cfg.llm)
    planner = PlannerAgent(bus, llm, cfg.planner)
    vision = VisionAgent(bus, make_detector(cfg.vision, llm), cfg.vision)
    nav = NavigatorAgent(bus, robot, cfg.navigator, cfg.robot.step_s)
    council = Council(bus, cfg.council, sinks)
    cc = cfg.council

    goal = planner.decompose(task)
    ar = goal.get("language") == "ar"
    emit("event", f"task: {task}  ->  target: {goal.get('target_en')}")
    facts = {"task": task, "target": goal.get("target_en"), "subgoals": "search, approach, stop close"}
    council.discuss("plan", facts, ar)
    last_round, sighted, avoiding = 0, False, False
    steps, reason = 0, "max steps reached"
    try:
        for steps in range(1, cfg.run.max_steps + 1):
            det = vision.step(robot.get_frame())
            prop = nav.propose()
            rev = planner.review()
            cmd = nav.act()
            if cfg.council.step_delay_s:
                time.sleep(cfg.council.step_delay_s)
            if steps % 10 == 1:
                emit("event", f"step {steps}: {cmd['action']}  dist={nav.distance:.0f}cm  seen={det.seen}")
            topic = None
            if planner.state.done:
                topic = "arrived"
            elif det.seen and not sighted:
                topic, sighted = "sighted", True
            elif prop.get("action") == "avoid" and not avoiding:
                topic = "obstacle"
            elif rev and not rev.get("approved"):
                topic = "veto"
            elif steps - last_round >= cc.every_steps:
                topic = "periodic"
            avoiding = prop.get("action") == "avoid"
            if topic and council.rounds < cc.max_rounds and (topic == "arrived" or steps - last_round >= cc.min_gap_steps):
                f = {"task": task, "target": goal.get("target_en"), "step": steps, "seen": det.seen, "bearing": round(det.bearing, 2),
                     "size": round(det.size, 2), "distance": f"{nav.distance:.0f}" if nav.distance < 1e6 else "no echo", "action": prop.get("action"), "why": prop.get("why"),
                     "planner_ruling": ("approved" if rev.get("approved") else f"vetoed ({rev.get('replacement')})") if rev else "none"}
                frame = robot.get_frame().jpeg if topic != "plan" else None
                if frame:
                    f["frame"] = frame
                council.discuss(topic, f, ar)
                last_round = steps
            if planner.state.done:
                reason = "target reached"
                break
    finally:
        try:
            robot.stop()
        except OSError as e:
            emit("note", f"could not send stop ({e}); the robot's own failsafe stops it within 0.6 s")
    res = RunResult(planner.state.done, steps, goal, reason)
    emit("event", f"{'SUCCESS' if res.success else 'FAILED'}: {res.reason} after {res.steps} steps")
    emit("finished", res.success)
    return res


def enable_ansi() -> None:
    """Old Windows consoles print color codes as junk unless virtual-terminal mode is switched on."""
    if sys.platform == "win32":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)
        except Exception:
            pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="sphinx1.demo", description="Live multi-model agent demo.")
    p.add_argument("--task", help='task, e.g. "find the red bottle" (with --web it can be typed in the browser instead)')
    p.add_argument("--config", default="config.toml")
    p.add_argument("--council", choices=["mock", "ollama", "openai"], help="what powers the four talking agents (default: config.toml)")
    p.add_argument("--base-url", help="Ollama / OpenAI-compatible URL for the council")
    p.add_argument("--planner-model"); p.add_argument("--vision-model"); p.add_argument("--navigator-model"); p.add_argument("--safety-model")
    p.add_argument("--robot", choices=["sim", "http"]); p.add_argument("--url")
    p.add_argument("--llm", choices=["mock", "ollama", "openai"], help="LLM for the planner's task parsing")
    p.add_argument("--model"); p.add_argument("--vision", choices=["sim", "vlm"])
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--web", action="store_true", help="serve the live browser view on http://localhost:8765")
    p.add_argument("--port", type=int, default=8765)
    a = p.parse_args(argv)
    enable_ansi()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass

    cfg = load_config(a.config)
    if a.council: cfg.council.provider = a.council
    if a.base_url: cfg.council.base_url = a.base_url
    for k in ("planner", "vision", "navigator", "safety"):
        v = getattr(a, f"{k}_model")
        if v: setattr(cfg.council, f"{k}_model", v)
    if a.robot: cfg.robot.kind = a.robot
    if a.url: cfg.robot.url = a.url
    if a.llm: cfg.llm.provider = a.llm
    if a.model: cfg.llm.model = a.model
    if a.vision: cfg.vision.backend = a.vision

    sinks = [ConsoleSink()]
    if not a.web:
        if not a.task:
            p.error("--task is required without --web")
        return 0 if run_demo(a.task, cfg, sinks, a.seed).success else 1

    from .webui import Hub, serve
    hub = Hub()
    sinks.append(hub)
    server = serve(hub, a.port, lambda task, seed: run_demo(task, cfg, sinks, seed))
    url = f"http://localhost:{a.port}"
    print(f"Live view: {url}  (type the judges' task there)")
    if not a.task:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    else:
        webbrowser.open(url)
        hub.wait_for_client(20)
        threading.Thread(target=run_demo, args=(a.task, cfg, sinks, a.seed), daemon=True).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Wire the three agents to a robot and run the loop."""
from __future__ import annotations

from dataclasses import dataclass

from .bus import Bus, Message
from .config import Config
from .llm import make_llm
from .navigator import NavigatorAgent
from .planner import PlannerAgent
from .robot import HTTPRobot, Robot, SimRobot
from .vision import VisionAgent, make_detector


@dataclass
class RunResult:
    success: bool
    steps: int
    goal: dict
    reason: str


def make_robot(cfg: Config, seed: int = 1) -> Robot:
    if cfg.robot.kind == "sim":
        return SimRobot(seed=seed)
    if cfg.robot.kind == "http":
        return HTTPRobot(cfg.robot.url)
    raise ValueError(f"unknown robot kind {cfg.robot.kind!r}; choose 'sim' or 'http'")


def format_message(m: Message) -> str:
    data = ", ".join(f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}" for k, v in m.data.items() if k != "task")
    return f"  [{m.sender:>9} -> {m.to:<9}] {m.kind:<11} {data}"


def run(task: str, cfg: Config, robot: Robot | None = None, seed: int = 1, verbose: bool = True) -> RunResult:
    bus = Bus(on_message=(lambda m: print(format_message(m))) if verbose else None)
    robot = robot or make_robot(cfg, seed)
    llm = make_llm(cfg.llm)
    planner = PlannerAgent(bus, llm, cfg.planner)
    vision = VisionAgent(bus, make_detector(cfg.vision, llm), cfg.vision)
    nav = NavigatorAgent(bus, robot, cfg.navigator, cfg.robot.step_s)

    goal = planner.decompose(task)
    steps, reason = 0, "max steps reached"
    try:
        for steps in range(1, cfg.run.max_steps + 1):
            vision.step(robot.get_frame())
            nav.propose()
            planner.review()
            nav.act()
            if planner.state.done:
                reason = "target reached"
                break
    finally:
        try:
            robot.stop()
        except OSError as e:  # network gone: the firmware failsafe stops the motors by itself
            print(f"warning: could not send stop ({e}); the robot's own failsafe stops it within 0.6 s")
    return RunResult(planner.state.done, steps, goal, reason)

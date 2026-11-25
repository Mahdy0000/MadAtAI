"""Config loading: TOML file -> dataclasses, with defaults for every field."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


@dataclass
class RobotCfg:
    kind: str = "sim"
    url: str = "http://192.168.4.1"
    step_s: float = 0.25


@dataclass
class LLMCfg:
    provider: str = "mock"
    model: str = "qwen2.5vl:7b"
    base_url: str = ""
    api_key_env: str = "OPENAI_API_KEY"
    timeout_s: float = 60


@dataclass
class VisionCfg:
    backend: str = "sim"
    min_confidence: float = 0.5


@dataclass
class NavigatorCfg:
    speed: int = 150
    turn_speed: int = 100
    stop_cm: float = 18
    arrive_cm: float = 22
    center_tolerance: float = 0.4


@dataclass
class PlannerCfg:
    max_search_turns: int = 12
    confirm_arrivals: int = 2


@dataclass
class RunCfg:
    max_steps: int = 300


@dataclass
class Config:
    robot: RobotCfg = field(default_factory=RobotCfg)
    llm: LLMCfg = field(default_factory=LLMCfg)
    vision: VisionCfg = field(default_factory=VisionCfg)
    navigator: NavigatorCfg = field(default_factory=NavigatorCfg)
    planner: PlannerCfg = field(default_factory=PlannerCfg)
    run: RunCfg = field(default_factory=RunCfg)


def load_config(path: str | Path | None = None) -> Config:
    """Load a TOML config. Missing file or missing keys fall back to defaults."""
    cfg = Config()
    if path is None or not Path(path).exists():
        return cfg
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    for section in fields(cfg):
        values = raw.get(section.name, {})
        target = getattr(cfg, section.name)
        for key, val in values.items():
            if not hasattr(target, key):
                raise ValueError(f"unknown config key [{section.name}] {key}")
            setattr(target, key, val)
    return cfg

"""Command line: python -m sphinx1 --task "find the red bottle"."""
from __future__ import annotations

import argparse
import sys

from .config import load_config
from .runner import run


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sphinx1", description="Run the Sphinx-1 agent team.")
    p.add_argument("--task", required=True, help='task in Arabic or English, e.g. "find the red bottle"')
    p.add_argument("--config", default="config.toml", help="path to config.toml (default: ./config.toml)")
    p.add_argument("--robot", choices=["sim", "http"], help="override robot.kind")
    p.add_argument("--url", help="robot URL for --robot http, e.g. http://192.168.1.50")
    p.add_argument("--llm", choices=["mock", "ollama", "openai"], help="override llm.provider")
    p.add_argument("--model", help="override llm.model")
    p.add_argument("--vision", choices=["sim", "vlm"], help="override vision.backend")
    p.add_argument("--seed", type=int, default=1, help="simulator layout seed")
    p.add_argument("--max-steps", type=int, help="override run.max_steps")
    p.add_argument("--quiet", action="store_true", help="do not print the agents' messages")
    a = p.parse_args(argv)

    cfg = load_config(a.config)
    if a.robot: cfg.robot.kind = a.robot
    if a.url: cfg.robot.url = a.url
    if a.llm: cfg.llm.provider = a.llm
    if a.model: cfg.llm.model = a.model
    if a.vision: cfg.vision.backend = a.vision
    if a.max_steps: cfg.run.max_steps = a.max_steps

    res = run(a.task, cfg, seed=a.seed, verbose=not a.quiet)
    print(f"\n{'SUCCESS' if res.success else 'FAILED'}: {res.reason} after {res.steps} steps. Target: {res.goal.get('target_en')}")
    return 0 if res.success else 1


if __name__ == "__main__":
    sys.exit(main())

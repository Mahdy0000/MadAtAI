# agents/

The laptop-side brain, Python package `sphinx1`. Setup and run commands are in the [top-level README](../README.md).

| Module | Role |
| --- | --- |
| `bus.py` | message bus the agents use to talk (every message is logged) |
| `planner.py` | task to goal (LLM, with a rule-based Arabic/English fallback); approves or vetoes navigator proposals |
| `vision.py` | `Detector` interface, simulator and VLM backends, the vision agent |
| `navigator.py` | observation + ultrasonic distance to motor commands, obstacle avoidance, stall detection |
| `llm.py` | `LLM` interface: Ollama, OpenAI-compatible, mock |
| `robot.py` | `Robot` interface: HTTP client for the ESP32-CAM, and a 2D simulator |
| `runner.py`, `__main__.py` | wiring and the CLI |
| `config.toml`, `config.py` | settings |

Only the Python standard library is used (plus `tomli` on Python 3.10).

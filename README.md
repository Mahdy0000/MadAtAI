# MadAtAI

> Mad at AI? Build one that actually does something. A $40 robot with a team of AI agents for a brain.

**Sphinx-1** is the robot's codename. **MadAtAI** is the project: our entry for the **Agentic AI** track at the AI Summit 2026 hackathon (Arab Open University, Dec 28-29, 2026).

A judge gives the robot a task in **Arabic or English** ("find the red bottle", "هات لي الزجاجة الحمرا"). Three agents on a laptop understand it, look through the robot's camera, plan, and drive the robot until it reaches the object and stops next to it. The robot itself is cheap (about $40 in parts). The intelligence is a multi-agent system that talks over a message bus: the **planner** reads the task and supervises, the **vision** agent finds the target in each frame, and the **navigator** proposes motor moves that the planner approves or vetoes.

## Tested and untested (honest list)

| Part | Status |
| --- | --- |
| Agent loop (bus, planner, vision, navigator) in the simulator | Run: unit tests pass, `python -m sphinx1` reaches the target in 35 of 40 simulated layouts |
| Arabic and English task parsing | Rule-based parser unit-tested on one sentence per language. LLM-based parsing: not tested with a real model |
| Ollama / OpenAI-compatible backends | Written, never run against a real model |
| VLM vision on real camera frames | Written, never run |
| HTTP robot client | Written, never run against the firmware |
| ESP32-CAM firmware | Written, **never compiled or flashed**. Not flash-verified |
| Motor failsafe (stops when Wi-Fi/laptop disappears) | Written, **untested on hardware**: do the safety test in `firmware/README.md` first |
| Wiring and pin map | Drawn from the board pinout, not yet built |

What the robot does: it **finds the object and drives up to it**, then stops. The current parts list has a wheeled chassis and no gripper or arm, so it does not pick anything up.

Status: v0.1 starter. The agent loop is tested in a simulator only. The firmware and the real-camera vision path are written but **not yet tested on hardware**. No benchmarks beyond the simulator numbers below.

## Run it now, no hardware (2 minutes)

You need Python 3.10 or newer.

```bash
git clone https://github.com/Mahdy0000/MadAtAI.git
cd MadAtAI/agents
```

Windows (PowerShell):
```powershell
.\setup.ps1
.\.venv\Scripts\python.exe -m sphinx1 --task "find the red bottle"
```

Linux / macOS:
```bash
./setup.sh
. .venv/bin/activate
python -m sphinx1 --task "find the red bottle"
```

You will see the three agents exchange messages and the run end with `SUCCESS: target reached after N steps`. Try Arabic: `python -m sphinx1 --task "هات لي الزجاجة الحمرا"`. Different room layout: `--seed 7`. Run the tests: `python -m unittest discover -s tests -t .`

Simulator only, measured with `--seed 1..40` and the default config: 35 of 40 layouts reached the target within 300 steps, 5 timed out. This says nothing about the real robot.

## Live demo: four models talking, streamed

`python -m sphinx1.demo --council ollama --web` opens a browser view where Planner, Vision, Navigator and Safety (each on its own Ollama model) discuss every decision live, token by token. Setup, dry-run checklist and the judges' script: [docs/DEMO.md](docs/DEMO.md). Works without any model too (scripted voices).

## Run it on the real robot

1. Build the robot: [docs/BOM.md](docs/BOM.md) and [docs/WIRING.md](docs/WIRING.md).
2. Flash the ESP32-CAM: [firmware/README.md](firmware/README.md) (exact Arduino IDE steps, Wi-Fi credentials go in `firmware/sphinx1_cam/config.h`). Note the IP it prints.
3. On the laptop, same Wi-Fi. Without any model (the planner uses its rule-based parser) you still need a vision backend, so use a local vision model with [Ollama](https://ollama.com):
   ```bash
   ollama pull qwen2.5vl:7b      # or any vision-capable model you prefer
   python -m sphinx1 --robot http --url http://<robot-ip> --llm ollama --model qwen2.5vl:7b --vision vlm --task "find the red bottle"
   ```
   Use an API instead: `--llm openai --model <model-name>` with the key in the `OPENAI_API_KEY` environment variable (any OpenAI-compatible server works, set `base_url` in `agents/config.toml`).

## Architecture

```
                 task (Arabic / English)
                          |
                          v
                 +-----------------+
                 |     Planner     |  LLM turns the task into a goal (rule-based fallback),
                 |      agent      |  approves or vetoes every move, declares success
                 +--------+--------+
                    ^     |  approve / veto + replacement
        proposal    |     v
      +-------------+----------+          observation (seen, bearing, size)
      |   Navigator agent      |<----------------------+
      | proposes motor moves,  |                       |
      | avoids obstacles       |               +-------+-------+
      +-----------+------------+               |  Vision agent |
                  | drive commands             | Detector:     |
                  v                            |  sim | VLM    |
      +------------------------------+         +-------+-------+
      |  Robot interface (HTTP/sim)  |---- JPEG frames -+
      +--------------+---------------+
                     | Wi-Fi
                     v
      +----------------------------------------+
      | ESP32-CAM  --  L298N  --  2 DC motors  |
      | camera        motor driver + HC-SR04   |
      +----------------------------------------+
```

How the negotiation works, each tick: vision posts an `observation`; navigator reads it plus the ultrasonic distance and posts a `proposal` (`spin`, `turn`, `approach`, `avoid`, `arrived`); the planner answers `approve` or `veto` with a replacement (`explore`, `hold`). Examples: after 12 scanning turns without finding the target the planner vetoes spinning and orders exploring forward; an `arrived` proposal is vetoed with `hold` until it repeats twice and vision still sees the target.

Swappable parts (all chosen in `agents/config.toml` or on the command line):

| Part | Options | Where |
| --- | --- | --- |
| LLM | `mock` (offline), `ollama`, `openai` (any OpenAI-compatible API) | `sphinx1/llm.py` |
| Vision | `sim` (simulator ground truth), `vlm` (asks the LLM about each frame); add your own `Detector` (YOLO, OWL-ViT...) | `sphinx1/vision.py` |
| Robot | `sim`, `http` (the ESP32-CAM) | `sphinx1/robot.py` |

## Layout

| Path | What |
| --- | --- |
| `agents/` | Python package `sphinx1`: bus, planner, vision, navigator, LLM backends, simulator, CLI, tests |
| `agents/config.toml` | all settings, documented inline |
| `firmware/sphinx1_cam/` | ESP32-CAM Arduino sketch and `config.h` (Wi-Fi, pins) |
| `firmware/README.md` | exact flashing steps and hardware bring-up checklist |
| `docs/DEMO.md` | live streaming demo: setup, dry run, judges' script |
| `docs/BOM.md`, `docs/WIRING.md` | parts list, wiring diagram, pin map |

## Roadmap

- [x] Concept, architecture
- [x] Agent loop + simulator + tests
- [x] Firmware v0.1 written
- [ ] Build the chassis, wire it, run the firmware bring-up checklist
- [ ] Tune the navigator on the real robot (turn speeds, camera field of view)
- [ ] Vision on real frames: try a few local vision models, keep the one that works
- [ ] Arabic task parsing with an LLM on real phrases
- [ ] Demo runs, record the 5 minute video, write the proposal (form closes Dec 3)

## License

No license file yet. Add one (MIT is typical) before the final submission.

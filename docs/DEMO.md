# Live demo: four agents, four models, talking in real time

Planner, Vision, Navigator and Safety are four agents, each backed by its own local model through Ollama.
They talk to each other in short rounds (what the plan is, what the camera sees, what move to make, is it safe),
and every word streams token by token over the message bus and onto a browser page for the judges.
The robot's motor control stays deterministic: the agents discuss and challenge each decision, they never send
raw motor commands from free text. If a model is down, that agent says a scripted line (marked "fallback") and the demo keeps going.

## Status (read this first)

- Tested: bus streaming, Ollama/OpenAI streaming parsers against a local fake server, scripted voices, full sim run, browser view over HTTP (all in `agents/tests/test_council.py`).
- NOT tested yet: with real Ollama models, on your GPU, or on the real robot. Do the 10-minute dry run below before the judges see it.

## One-time setup (Windows)

1. Install Ollama from https://ollama.com and open a new PowerShell.
2. Pull the four models (about 9 GB in total, fits in 12 GB VRAM together):
   ```powershell
   ollama pull qwen2.5:3b
   ollama pull qwen2.5vl:3b
   ollama pull llama3.2:3b
   ollama pull gemma2:2b
   ```
3. Keep all four loaded at once so turns do not wait for model swaps. Set this, then restart Ollama (quit it from the tray and start it again):
   ```powershell
   setx OLLAMA_MAX_LOADED_MODELS 4
   ```
4. In the `agents` folder run `.\setup.ps1` once (same as the main README).

## Run it

Browser view (best for judges, handles Arabic text properly):
```powershell
cd agents
.\.venv\Scripts\python.exe -m sphinx1.demo --council ollama --web
```
A page opens at http://localhost:8765 with four columns. Type the judges' task in the box (Arabic or English) and press Run.

Terminal only: `.\.venv\Scripts\python.exe -m sphinx1.demo --council ollama --task "find the red bottle"`

Without any model, to check the plumbing: leave out `--council ollama` (scripted voices, same screen).

Different models: `--planner-model`, `--vision-model`, `--navigator-model`, `--safety-model`, or edit `[council]` in `agents/config.toml`.
Any OpenAI-compatible server: `--council openai --base-url http://localhost:1234/v1` (LM Studio) with the model names set.

On the real robot add: `--robot http --url http://<robot-ip> --vision vlm --llm ollama --model qwen2.5vl:3b`.
The Vision agent then also looks at the actual camera frame. Do the wheels-up safety test in `firmware/README.md` first.

## Dry run checklist (before the judges)

1. Run the browser view, task `find the red bottle`. Expect four columns filling with live text and the run ending `SUCCESS`.
2. If a line shows "fallback line (model unavailable)": that model name is not pulled or Ollama is not running. `ollama list` shows what you have.
3. If turns are slow (more than about 5 s per line): the models are swapping. Check step 3 above, or use smaller ones (`qwen2.5:1.5b`).
4. Try an Arabic task: `هات لي الزجاجة الحمرا`.
5. Unplug the network cable / Wi-Fi from Ollama's side (stop Ollama) and confirm the demo still finishes with fallback lines.

## Script for the judges (about 3 minutes)

1. (20 s) "This robot costs about 40 dollars. The intelligence is not in the robot, it is a team of four AI agents on this laptop, each running a different model."
2. (10 s) Point at the four columns: Planner decides, Vision sees, Navigator drives, Safety can object.
3. (30 s) Ask a judge to type any task, Arabic or English, for example the red bottle. Press Run.
4. (60 s) While it streams, narrate: "Planner splits the task. Vision reports what it sees. Navigator proposes a move. Safety checks the distance. Watch the planner overrule the navigator when needed." Point out the live tokens: nobody is reading a log after the fact.
5. (20 s) When it ends: "It found the target and stopped next to it. The motors only follow approved moves, and the firmware stops the wheels by itself if Wi-Fi drops."
6. (20 s) Be honest about limits if asked: "It finds the object and drives up to it, it has no gripper. Language is Arabic and English."

If the robot misbehaves live: switch to the simulator (`--robot sim`), same screen, same agents.

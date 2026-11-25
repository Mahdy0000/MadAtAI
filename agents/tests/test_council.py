import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from sphinx1.bus import Bus
from sphinx1.config import Config, CouncilCfg
from sphinx1.council import Council, ORDER
from sphinx1.demo import run_demo


class Rec:
    def __init__(self): self.ev = []
    def round(self, t, n): self.ev.append(("round", t))
    def start(self, a, m): self.ev.append(("start", a, m))
    def token(self, a, t): self.ev.append(("token", a, t))
    def end(self, a, t, fb): self.ev.append(("end", a, t, fb))
    def note(self, t): self.ev.append(("note", t))
    def event(self, t): self.ev.append(("event", t))
    def finished(self, ok): self.ev.append(("finished", ok))


class FakeOllama(BaseHTTPRequestHandler):
    """Streams the model name back token by token, like Ollama's /api/chat."""
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["stream"] is True
        self.send_response(200); self.end_headers()
        for w in (f"I am {body['model']}", " speaking", " live."):
            self.wfile.write((json.dumps({"message": {"content": w}, "done": False}) + "\n").encode()); self.wfile.flush()
        self.wfile.write((json.dumps({"message": {"content": ""}, "done": True}) + "\n").encode())


class CouncilTests(unittest.TestCase):
    def test_bus_stream(self):
        bus = Bus(); bus.register("a"); bus.register("b"); seen = []
        bus.stream("a", "b", "say", iter(["he", "llo"]), seen.append)
        self.assertEqual(seen, ["he", "llo"])
        self.assertEqual(bus.receive("b")[0].data["text"], "hello")

    def test_scripted_round_all_four_speak(self):
        rec = Rec(); cfg = CouncilCfg(token_delay_s=0)
        turns = Council(Bus(), cfg, [rec]).discuss("plan", {"target": "red bottle"})
        self.assertEqual([t.agent for t in turns], ORDER)
        self.assertTrue(all(t.text and not t.fallback for t in turns))

    def test_streams_from_ollama_four_models(self):
        srv = HTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        cfg = CouncilCfg(provider="ollama", base_url=f"http://127.0.0.1:{srv.server_port}", token_delay_s=0)
        rec = Rec()
        turns = Council(Bus(), cfg, [rec]).discuss("sighted", {"target": "red bottle", "seen": True, "bearing": 0.2})
        srv.shutdown()
        self.assertEqual(len({t.model for t in turns}), 4)
        self.assertTrue(all(not t.fallback and t.text == f"I am {t.model} speaking live." for t in turns))
        self.assertGreaterEqual(len([e for e in rec.ev if e[0] == "token"]), 12)   # arrived in pieces

    def test_unreachable_model_falls_back(self):
        rec = Rec()
        cfg = CouncilCfg(provider="ollama", base_url="http://127.0.0.1:9", token_delay_s=0, timeout_s=2)
        turns = Council(Bus(), cfg, [rec]).discuss("plan", {"target": "red bottle"})
        self.assertTrue(all(t.fallback for t in turns))

    def test_demo_run_sim(self):
        rec = Rec(); cfg = Config()
        cfg.council.token_delay_s = 0; cfg.council.step_delay_s = 0
        res = run_demo("هات لي الزجاجة الحمرا", cfg, [rec], seed=1)
        self.assertTrue(res.success)
        self.assertGreaterEqual(len([e for e in rec.ev if e[0] == "round"]), 2)


if __name__ == "__main__":
    unittest.main()

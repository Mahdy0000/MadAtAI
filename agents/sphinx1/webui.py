"""Browser view for the live demo: four columns, one per agent, tokens appear as they stream. Standard library only.

The page also has a box where a judge types a task (Arabic or English) to start a run.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><title>MadAtAI live</title>
<style>
body{margin:0;background:#0b1020;color:#e8ecf5;font:16px system-ui,Segoe UI,sans-serif}
header{display:flex;gap:12px;align-items:center;padding:14px 20px;background:#121936}
h1{font-size:20px;margin:0 16px 0 0}input{flex:1;padding:10px;border-radius:8px;border:0;font-size:16px}
button{padding:10px 18px;border:0;border-radius:8px;background:#3b82f6;color:#fff;font-size:16px;cursor:pointer}
#cols{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;padding:16px}
.col{background:#121936;border-radius:12px;padding:12px;min-height:60vh;border-top:4px solid var(--c)}
.col h2{margin:0 0 2px;font-size:18px;color:var(--c);text-transform:capitalize}.col small{color:#8b95b5}
.msg{margin:10px 0;padding:10px;background:#1a2347;border-radius:8px;line-height:1.5;unicode-bidi:plaintext}
.fb{color:#8b95b5;font-size:12px}
#log{padding:0 20px 20px;color:#8b95b5;font:13px ui-monospace,Consolas,monospace;max-height:22vh;overflow:auto}
.round{grid-column:1/-1;color:#8b95b5;font-size:13px;margin:4px 0}
</style>
<header><h1>MadAtAI</h1><input id="t" dir="auto" placeholder="Task / المهمة: find the red bottle &nbsp;|&nbsp; هات لي الزجاجة الحمرا" value="find the red bottle">
<button onclick="go()">Run</button></header>
<div id="cols"></div><div id="log"></div>
<script>
const C={planner:'#60a5fa',vision:'#34d399',navigator:'#fbbf24',safety:'#f87171'};
const cols={};for(const a in C){const d=document.createElement('div');d.className='col';d.style.setProperty('--c',C[a]);
d.innerHTML='<h2>'+a+'</h2><small id="m-'+a+'"></small><div id="b-'+a+'"></div>';document.getElementById('cols').append(d);cols[a]=d}
let cur={};const log=document.getElementById('log');
function go(){fetch('/run',{method:'POST',body:JSON.stringify({task:document.getElementById('t').value})});
for(const a in C)document.getElementById('b-'+a).innerHTML='';log.innerHTML=''}
function note(t){const p=document.createElement('div');p.textContent=t;log.append(p);log.scrollTop=1e9}
const es=new EventSource('/events');es.onmessage=e=>{const m=JSON.parse(e.data);
if(m.type=='start'){document.getElementById('m-'+m.agent).textContent=m.model;const d=document.createElement('div');d.className='msg';
document.getElementById('b-'+m.agent).append(d);cur[m.agent]=d}
else if(m.type=='token'){cur[m.agent].textContent+=m.text}
else if(m.type=='end'){cur[m.agent].textContent=m.text;if(m.fallback){const f=document.createElement('div');f.className='fb';f.textContent='fallback line (model unavailable)';cur[m.agent].append(f)}}
else if(m.type=='round'){note('--- round '+m.n+': '+m.topic+' ---')}
else if(m.type=='reset'){for(const a in C)document.getElementById('b-'+a).innerHTML='';log.innerHTML=''}
else note(m.text||m.type)}
</script></html>"""


class Hub:
    """Sink that records every event and fans it out to the connected browsers."""

    def __init__(self):
        self.events: list[dict] = []
        self.subs: list[queue.Queue] = []
        self.lock = threading.Lock()
        self.clients = threading.Event()

    def _push(self, ev: dict) -> None:
        with self.lock:
            self.events.append(ev)
            for q in self.subs:
                q.put(ev)

    def round(self, topic, n): self._push({"type": "round", "topic": topic, "n": n})
    def start(self, agent, model): self._push({"type": "start", "agent": agent, "model": model})
    def token(self, agent, text): self._push({"type": "token", "agent": agent, "text": text})
    def end(self, agent, text, fallback): self._push({"type": "end", "agent": agent, "text": text, "fallback": fallback})
    def note(self, text): self._push({"type": "note", "text": text})
    def event(self, text): self._push({"type": "event", "text": text})
    def finished(self, ok): self._push({"type": "finished", "text": "finished: " + ("success" if ok else "failed")})

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self.lock:
            for ev in self.events:
                q.put(ev)
            self.subs.append(q)
        self.clients.set()
        return q

    def wait_for_client(self, timeout: float) -> None:
        self.clients.wait(timeout)
        time.sleep(0.5)


def serve(hub: Hub, port: int, on_run) -> ThreadingHTTPServer:
    busy = threading.Lock()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def do_GET(self):
            if self.path == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                q = hub.subscribe()
                try:
                    while True:
                        try:
                            ev = q.get(timeout=15)
                            self.wfile.write(f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode())
                        except queue.Empty:
                            self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    with hub.lock:
                        if q in hub.subs:
                            hub.subs.remove(q)
            else:
                body = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def do_POST(self):
            if self.path != "/run":
                self.send_error(404)
                return
            n = int(self.headers.get("Content-Length", 0))
            try:
                task = str(json.loads(self.rfile.read(n) or b"{}").get("task", "")).strip()
            except json.JSONDecodeError:
                task = ""
            ok = bool(task) and busy.acquire(blocking=False)
            if ok:
                def runner():
                    try:
                        hub._push({"type": "reset"})
                        on_run(task, 1)
                    finally:
                        busy.release()
                # on_run starts its own thread; release the lock when that finishes via wrapper below
                runner_thread = threading.Thread(target=runner, daemon=True)
                runner_thread.start()
            self.send_response(202 if ok else 409)
            self.end_headers()

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv

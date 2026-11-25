"""Navigator agent: turns the vision report and the ultrasonic reading into motor commands.

It does not act on its own. Each tick it sends the planner a *proposal*; it then drives
whatever the planner approved (its own proposal) or substituted (veto + replacement).
"""
from __future__ import annotations

from .bus import Bus
from .config import NavigatorCfg
from .robot import NO_ECHO, Robot


class NavigatorAgent:
    name = "navigator"

    def __init__(self, bus: Bus, robot: Robot, cfg: NavigatorCfg, step_s: float):
        self.bus, self.robot, self.cfg, self.step_s = bus, robot, cfg, step_s
        self.obs = {"seen": False, "bearing": 0.0, "size": 0.0, "confidence": 0.0}
        self.spin_dir = 1          # +1 spin right, -1 spin left
        self.avoid_dir = 1
        self.distance = NO_ECHO
        self.proposal: dict = {}
        self.last_action = ""
        self.recent: list[tuple[str, float]] = []   # (action, distance) of the last few steps, for stall detection
        bus.register(self.name)

    # -- phase 1: read sensors, propose
    def propose(self) -> dict:
        for m in self.bus.receive(self.name, "observation"):
            self.obs = m.data
        c, o = self.cfg, self.obs
        self.distance = d = self.robot.distance_cm()
        if o["seen"]:
            self.spin_dir = 1 if o["bearing"] >= 0 else -1
        stalled = self._stalled()
        centered = o["seen"] and abs(o["bearing"]) <= c.center_tolerance

        if centered and d <= c.arrive_cm:
            p = {"action": "arrived", "left": 0, "right": 0, "why": f"target centered at {d:.0f} cm"}
        elif stalled:
            if self.last_action != "avoid":
                self.avoid_dir = -self.avoid_dir
            t = c.turn_speed * self.avoid_dir
            p = {"action": "avoid", "left": t, "right": -t, "why": "wheels moving but the distance is not changing, probably stuck: turning away"}
        elif d < c.stop_cm and not centered:
            if self.last_action != "avoid":
                self.avoid_dir = -self.avoid_dir   # pick a new turn direction per obstacle, keep it while avoiding
            if d < c.stop_cm * 0.6:
                p = {"action": "avoid", "left": -c.speed, "right": -c.speed, "why": f"obstacle at {d:.0f} cm, backing up"}
            else:
                t = c.turn_speed * self.avoid_dir
                p = {"action": "avoid", "left": t, "right": -t, "why": f"obstacle at {d:.0f} cm, turning away"}
        elif o["seen"] and not centered:
            # pivot in place toward the target; speed proportional to the error, but never too weak to move the wheels
            t = int(max(60, min(c.turn_speed, abs(o["bearing"]) * 110)))
            t = t if o["bearing"] > 0 else -t
            p = {"action": "turn", "left": t, "right": -t, "why": f"centering target (bearing {o['bearing']:+.2f})"}
        elif o["seen"]:
            slow = 0.5 if d < 60 else 1.0
            turn = o["bearing"] * c.speed * 0.4
            p = {"action": "approach", "left": int(c.speed * slow + turn), "right": int(c.speed * slow - turn),
                 "why": f"driving at target, bearing {o['bearing']:+.2f}"}
        else:
            t = c.turn_speed * self.spin_dir
            p = {"action": "spin", "left": t, "right": -t, "why": "target not in view, scanning"}
        self.proposal = p
        self.bus.send(self.name, "planner", "proposal", **p)
        return p

    def _stalled(self, n: int = 6) -> bool:
        """Driving forward for n steps while a finite distance reading stays within 1.5 cm."""
        last = self.recent[-n:]
        if len(last) < n or any(a not in ("approach", "explore") for a, _ in last):
            return False
        ds = [d for _, d in last]
        return all(d != NO_ECHO for d in ds) and max(ds) - min(ds) < 1.5

    # -- phase 2: act on the planner's answer
    def act(self) -> dict:
        c = self.cfg
        cmd = self.proposal
        for m in self.bus.receive(self.name):
            if m.kind == "veto":
                rep = m.data.get("replacement", "hold")
                if rep == "explore":
                    if self.distance < c.stop_cm:
                        t = c.turn_speed * self.avoid_dir
                        cmd = {"action": "avoid", "left": t, "right": -t, "why": "explore blocked, turning"}
                    else:
                        cmd = {"action": "explore", "left": c.speed, "right": int(c.speed * 0.8), "why": "planner: explore forward"}
                else:
                    cmd = {"action": "hold", "left": 0, "right": 0, "why": "planner: hold and look again"}
        self.robot.drive(cmd["left"], cmd["right"], self.step_s)
        self.last_action = cmd["action"]
        self.recent.append((cmd["action"], self.distance))
        del self.recent[:-12]
        return cmd

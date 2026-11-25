"""Robot interface, the real HTTP robot, and a 2D simulator.

Both implement `Robot`, so agents cannot tell them apart.

HTTP API served by firmware/sphinx1_cam:
    GET /jpg                one JPEG camera frame
    GET /distance           forward distance in cm (-1 = no echo)
    GET /drive?l=..&r=..    motor speeds -255..255 (robot stops by itself if commands stop)
    GET /stop               stop motors
"""
from __future__ import annotations

import math
import random
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

NO_ECHO = float("inf")


@dataclass
class Frame:
    jpeg: bytes | None                 # None in the simulator
    meta: dict = field(default_factory=dict)   # simulator ground truth, empty on real hardware


class Robot(ABC):
    @abstractmethod
    def get_frame(self) -> Frame: ...

    @abstractmethod
    def distance_cm(self) -> float:
        """Forward distance from the ultrasonic sensor. NO_ECHO (inf) if nothing in range."""

    @abstractmethod
    def drive(self, left: int, right: int, duration_s: float) -> None:
        """Run motors (-255..255 each) for duration_s, then they stop."""

    @abstractmethod
    def stop(self) -> None: ...


class HTTPRobot(Robot):
    def __init__(self, base_url: str, timeout: float = 3.0):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str) -> bytes:
        with urllib.request.urlopen(self.base + path, timeout=self.timeout) as r:
            return r.read()

    def get_frame(self) -> Frame:
        return Frame(self._get("/jpg"))

    def distance_cm(self) -> float:
        v = float(self._get("/distance").decode().strip())
        return NO_ECHO if v < 0 else v

    def drive(self, left: int, right: int, duration_s: float) -> None:
        import time

        self._get(f"/drive?l={int(left)}&r={int(right)}")
        time.sleep(duration_s)
        self.stop()

    def stop(self) -> None:
        self._get("/stop")


# ---------------------------------------------------------------- simulator

@dataclass
class Circle:
    x: float
    y: float
    r: float


class SimRobot(Robot):
    """Differential-drive robot in a square arena (units: cm, angles: radians).

    Not a physics engine: kinematics, circle obstacles, a ray-cast ultrasonic sensor and a
    camera with a field of view. Enough to exercise the agent loop end to end.
    """

    ARENA = 400.0
    MAX_SPEED = 30.0       # cm/s at PWM 255
    TRACK = 12.0           # wheel separation, cm
    FOV = math.radians(60)
    SONAR_RANGE = 200.0
    CAM_RANGE = 350.0

    def __init__(self, seed: int = 1, n_obstacles: int = 4):
        rnd = random.Random(seed)
        self.x, self.y, self.th = 40.0, 40.0, rnd.uniform(0, math.pi / 2)
        self.target = Circle(rnd.uniform(150, 290), rnd.uniform(150, 290), 5.0)
        self.obstacles: list[Circle] = []
        while len(self.obstacles) < n_obstacles:
            c = Circle(rnd.uniform(80, 360), rnd.uniform(80, 360), rnd.uniform(10, 16))
            if math.dist((c.x, c.y), (self.x, self.y)) > 45 and math.dist((c.x, c.y), (self.target.x, self.target.y)) > 40:
                self.obstacles.append(c)
        self.time = 0.0

    # --- geometry helpers
    def _ray(self, angle: float, circles: list[Circle], max_d: float) -> tuple[float, Circle | None]:
        """Distance along a ray from the robot to the first circle or wall."""
        dx, dy = math.cos(angle), math.sin(angle)
        best, hit = max_d, None
        for c in circles:
            fx, fy = self.x - c.x, self.y - c.y
            b = fx * dx + fy * dy
            disc = b * b - (fx * fx + fy * fy - c.r * c.r)
            if disc >= 0:
                t = -b - math.sqrt(disc)
                if 0 <= t < best:
                    best, hit = t, c
        for t in (
            (0 - self.x) / dx if dx < -1e-9 else (self.ARENA - self.x) / dx if dx > 1e-9 else None,
            (0 - self.y) / dy if dy < -1e-9 else (self.ARENA - self.y) / dy if dy > 1e-9 else None,
        ):
            if t is not None and 0 <= t < best:
                best, hit = t, None
        return best, hit

    def distance_cm(self) -> float:
        d, _ = self._ray(self.th, self.obstacles + [self.target], self.SONAR_RANGE)
        return NO_ECHO if d >= self.SONAR_RANGE else d

    def get_frame(self) -> Frame:
        dx, dy = self.target.x - self.x, self.target.y - self.y
        dist = math.hypot(dx, dy)
        off = (math.atan2(dy, dx) - self.th + math.pi) % (2 * math.pi) - math.pi
        visible = dist <= self.CAM_RANGE and abs(off) <= self.FOV / 2
        if visible:  # line of sight: nothing in front of the target along that ray
            d_hit, hit = self._ray(math.atan2(dy, dx), self.obstacles, dist)
            visible = hit is None or d_hit >= dist - 1e-6
        width = min(1.0, 2 * math.atan(self.target.r / max(dist, 1e-3)) / self.FOV)
        meta = {"visible": bool(visible), "bearing": -off / (self.FOV / 2), "size": width, "dist": dist}
        return Frame(None, meta)

    def drive(self, left: int, right: int, duration_s: float) -> None:
        vl = max(-255, min(255, left)) / 255 * self.MAX_SPEED
        vr = max(-255, min(255, right)) / 255 * self.MAX_SPEED
        v, w = (vl + vr) / 2, (vr - vl) / self.TRACK
        n = max(1, int(duration_s / 0.02))
        dt = duration_s / n
        for _ in range(n):
            self.th += w * dt
            nx, ny = self.x + v * math.cos(self.th) * dt, self.y + v * math.sin(self.th) * dt
            if self._free(nx, ny):
                self.x, self.y = nx, ny
        self.time += duration_s

    def _free(self, x: float, y: float) -> bool:
        """A move is blocked only if it ends inside a wall/obstacle margin AND gets closer to it,
        so the robot can always back away from something it is touching."""
        if self._wall_gap(x, y) < 6 and self._wall_gap(x, y) < self._wall_gap(self.x, self.y):
            return False
        for c in self.obstacles + [self.target]:
            now, new = math.hypot(self.x - c.x, self.y - c.y), math.hypot(x - c.x, y - c.y)
            if new <= c.r + 6 and new < now:
                return False
        return True

    def _wall_gap(self, x: float, y: float) -> float:
        return min(x, y, self.ARENA - x, self.ARENA - y)

    def stop(self) -> None:
        pass

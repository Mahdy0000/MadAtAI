"""Vision agent and its detector backends.

A Detector answers one question about one frame: where is the target, if anywhere?
Swap the backend with [vision] backend in config.toml, or write your own Detector
(for example YOLO or OWL-ViT) and register it in make_detector.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass

from .bus import Bus
from .config import VisionCfg
from .llm import LLM, parse_json
from .robot import Frame


@dataclass
class Detection:
    seen: bool = False
    bearing: float = 0.0       # -1 (far left) .. +1 (far right), 0 = straight ahead
    size: float = 0.0          # width of the target as a fraction of the frame, 0..1
    confidence: float = 0.0


class Detector(ABC):
    @abstractmethod
    def detect(self, frame: Frame, target: str) -> Detection: ...


class SimDetector(Detector):
    """Reads the simulator's ground truth. Only works with the simulated robot."""

    def detect(self, frame, target):
        m = frame.meta
        if not m:
            raise RuntimeError("vision.backend='sim' needs the simulated robot (robot.kind='sim')")
        if not m["visible"]:
            return Detection()
        return Detection(True, m["bearing"], m["size"], 0.9)


class VLMDetector(Detector):
    """Asks a vision-language model (via the LLM interface) to locate the target in the JPEG."""

    SYSTEM = (
        "You are the eyes of a small robot. You get one camera image and a target description. "
        'Reply with JSON only: {"found": true|false, "x_center": 0..1, "width": 0..1, "confidence": 0..1}. '
        "x_center is the horizontal center of the target in the image (0 = left edge, 1 = right edge); "
        "width is its width as a fraction of the image width. If the target is not visible, found is false."
    )

    def __init__(self, llm: LLM):
        self.llm = llm

    def detect(self, frame, target):
        if frame.jpeg is None:
            raise RuntimeError("vision.backend='vlm' needs real camera frames (robot.kind='http')")
        out = parse_json(self.llm.chat(self.SYSTEM, f"Target: {target}", frame.jpeg, json_mode=True))
        if not out.get("found"):
            return Detection()
        try:
            x = min(1.0, max(0.0, float(out.get("x_center", 0.5))))
            return Detection(True, (x - 0.5) * 2, min(1.0, max(0.0, float(out.get("width", 0.0)))),
                             min(1.0, max(0.0, float(out.get("confidence", 0.5)))))
        except (TypeError, ValueError):
            return Detection()


def make_detector(cfg: VisionCfg, llm: LLM) -> Detector:
    if cfg.backend == "sim":
        return SimDetector()
    if cfg.backend == "vlm":
        return VLMDetector(llm)
    raise ValueError(f"unknown vision backend {cfg.backend!r}; choose 'sim' or 'vlm'")


class VisionAgent:
    name = "vision"

    def __init__(self, bus: Bus, detector: Detector, cfg: VisionCfg):
        self.bus, self.detector, self.cfg = bus, detector, cfg
        self.target = ""
        bus.register(self.name)

    def step(self, frame: Frame) -> Detection:
        for m in self.bus.receive(self.name, "goal"):
            self.target = m.data["target_en"]
        det = self.detector.detect(frame, self.target)
        if det.seen and det.confidence < self.cfg.min_confidence:
            det = Detection()  # too unsure to steer on
        self.bus.send(self.name, "navigator", "observation", **asdict(det))
        self.bus.send(self.name, "planner", "observation", **asdict(det))
        return det

import unittest

from sphinx1.bus import Bus
from sphinx1.config import Config, load_config
from sphinx1.llm import MockLLM, parse_json
from sphinx1.planner import PlannerAgent, rule_based_goal
from sphinx1.robot import SimRobot
from sphinx1.runner import run


class BusTests(unittest.TestCase):
    def test_direct_and_broadcast(self):
        bus = Bus()
        for n in ("a", "b", "c"):
            bus.register(n)
        bus.send("a", "b", "hello", x=1)
        bus.send("a", "all", "note")
        self.assertEqual([m.kind for m in bus.receive("b")], ["hello", "note"])
        self.assertEqual([m.kind for m in bus.receive("c")], ["note"])
        self.assertEqual(bus.receive("a"), [])


class PlannerTests(unittest.TestCase):
    def test_english(self):
        self.assertEqual(rule_based_goal("bring me the red bottle")["target_en"], "red bottle")

    def test_arabic(self):
        g = rule_based_goal("هات لي الزجاجة الحمرا")
        self.assertEqual((g["language"], g["target_en"]), ("ar", "red bottle"))

    def test_llm_json_is_used_when_valid(self):
        class Fake(MockLLM):
            def chat(self, *a, **k):
                return 'sure! {"language":"en","target_en":"blue cup","target_original":"cup","subgoals":[]}'

        p = PlannerAgent(Bus(), Fake(), Config().planner)
        self.assertEqual(p.decompose("get a cup")["target_en"], "blue cup")

    def test_llm_failure_falls_back(self):
        class Broken(MockLLM):
            def chat(self, *a, **k):
                raise OSError("no network")

        p = PlannerAgent(Bus(), Broken(), Config().planner)
        self.assertEqual(p.decompose("find the green ball")["target_en"], "green ball")

    def test_parse_json_junk(self):
        self.assertEqual(parse_json("no json here"), {})


class SimRunTests(unittest.TestCase):
    def test_sim_finds_target(self):
        res = run("find the red bottle", Config(), seed=1, verbose=False)
        self.assertTrue(res.success, res)

    def test_arabic_task_in_sim(self):
        res = run("هات لي الزجاجة الحمرا", Config(), seed=2, verbose=False)
        self.assertTrue(res.success, res)

    def test_sonar_sees_wall_or_nothing_in_open_space(self):
        r = SimRobot(seed=1)
        self.assertGreater(r.distance_cm(), 0)

    def test_config_file_loads(self):
        self.assertEqual(load_config("config.toml").robot.kind, "sim")


if __name__ == "__main__":
    unittest.main()

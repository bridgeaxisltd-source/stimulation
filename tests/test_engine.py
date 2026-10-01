import json
import random
import tempfile
import unittest
from dataclasses import replace

from stimulation import MatchEngine, Team, load_players, run_simulations
from stimulation.data_loader import DEFAULT_DATA_PATH, PlayerDataError
from stimulation.models import PERSONALITY_KEYS


class PlayerDataTests(unittest.TestCase):
    def test_default_data_loads_both_players(self):
        players = load_players()
        self.assertEqual(set(players), {"messi", "ronaldo"})

    def test_out_of_range_attribute_is_rejected(self):
        with open(DEFAULT_DATA_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        data["players"][0]["attributes"]["pace"] = 140
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(data, tmp)
        with self.assertRaises(PlayerDataError):
            load_players(tmp.name)


class EngineTests(unittest.TestCase):
    def setUp(self):
        p = load_players()
        self.messi = Team("Messi", p["messi"])
        self.ronaldo = Team("Ronaldo", p["ronaldo"])

    def test_same_seed_same_match(self):
        a = MatchEngine(self.messi, self.ronaldo, random.Random(7)).play()
        b = MatchEngine(self.messi, self.ronaldo, random.Random(7)).play()
        self.assertEqual(a.goals, b.goals)
        self.assertEqual(a.stats[0].passes_attempted, b.stats[0].passes_attempted)

    def test_stats_are_consistent(self):
        for seed in range(20):
            m = MatchEngine(self.messi, self.ronaldo, random.Random(seed)).play()
            for s in m.stats:
                self.assertLessEqual(s.goals, s.shots_on_target)
                self.assertLessEqual(s.shots_on_target, s.shots)
                self.assertLessEqual(s.passes_completed, s.passes_attempted)
                self.assertEqual(s.goals, sum(s.goal_types.values()))
            self.assertEqual(len(m.goal_log), sum(m.goals))
            self.assertAlmostEqual(m.possession_pct(0) + m.possession_pct(1), 100.0)

    def test_knockout_always_has_a_winner(self):
        for seed in range(30):
            m = MatchEngine(self.messi, self.ronaldo, random.Random(seed), knockout=True).play()
            self.assertIsNotNone(m.winner)

    def test_mirror_match_is_balanced(self):
        """Same player on both sides must come out roughly even, or the engine is biased."""
        s = run_simulations(self.messi, replace(self.messi, name="Messi B"), matches=1500, seed=1)
        self.assertLess(abs(s.win_rate(0) - s.win_rate(1)), 0.06)

    def test_ronaldos_dominate_the_air(self):
        s = run_simulations(self.messi, self.ronaldo, matches=200, seed=3)
        self.assertGreater(s.avg(1, "aerials_won"), s.avg(0, "aerials_won"))
        self.assertGreater(s.goal_types[1]["header"], s.goal_types[0]["header"])

    def test_messis_keep_the_ball(self):
        s = run_simulations(self.messi, self.ronaldo, matches=200, seed=3)
        self.assertGreater(s.avg_possession(0), 50)

    def test_parallel_matches_serial(self):
        serial = run_simulations(self.messi, self.ronaldo, matches=40, seed=9, workers=1)
        parallel = run_simulations(self.messi, self.ronaldo, matches=40, seed=9, workers=2)
        self.assertEqual(serial.wins, parallel.wins)
        self.assertEqual(serial.scorelines, parallel.scorelines)

    def test_neutral_personality_changes_behaviour(self):
        neutral = replace(self.ronaldo.player, personality={k: 50 for k in PERSONALITY_KEYS})
        ego = run_simulations(self.messi, self.ronaldo, matches=200, seed=5)
        calm = run_simulations(self.messi, Team("Ronaldo", neutral), matches=200, seed=5)
        # High-ego Ronaldos shoot from distance far more often.
        self.assertGreater(ego.goal_types[1]["long"], calm.goal_types[1]["long"])


if __name__ == "__main__":
    unittest.main()

import unittest

from Sys.RootCauseAnalyze.skill_pipeline import _combine_scores


class SkillPipelineDeterminismTest(unittest.TestCase):
    def test_tied_scores_use_stable_ip_tiebreaker(self):
        scores = {
            2: {
                "10.0.0.2": 1.0,
                "10.0.0.1": 1.0,
                "10.0.0.3": 0.5,
            }
        }

        first = _combine_scores(scores, ["10.0.0.2", "10.0.0.1", "10.0.0.3"])
        second = _combine_scores(scores, ["10.0.0.3", "10.0.0.1", "10.0.0.2"])

        self.assertEqual(first, second)
        self.assertEqual(first, ["10.0.0.1", "10.0.0.2", "10.0.0.3"])


if __name__ == "__main__":
    unittest.main()

import unittest

from Sys.RootCauseAnalyze.skill_pipeline import _combine_scores, rank_devices_by_skills


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

    def test_skill_details_include_own_rankings_and_trust_trees(self):
        node_list = [
            {
                "mgmt_ip": "10.0.0.1",
                "cross": 3,
                "linked_to": ["10.0.0.2"],
                "linked_from": [],
                "alarms": [{"alarm_name": "trunkdown", "alarm_time": 1000}],
                "logs": [{"alarm_time": 1100}],
            },
            {
                "mgmt_ip": "10.0.0.2",
                "cross": 0,
                "linked_to": [],
                "linked_from": ["10.0.0.1"],
                "alarms": [{"alarm_name": "minor", "alarm_time": 5000}],
                "logs": [],
            },
            {
                "mgmt_ip": "10.0.0.3",
                "cross": 0,
                "linked_to": [],
                "linked_from": [],
                "alarms": [],
                "logs": [],
            },
        ]

        predicted, details = rank_devices_by_skills(
            node_list,
            {"alarm_time": 1000},
            skill_ids=(1, 2),
            top_k=3,
            weight_dirpath=None,
        )

        self.assertTrue(predicted)
        self.assertIn("combined", details)
        self.assertIn("topk", details["combined"])
        self.assertIn("trust_tree", details["1"])
        self.assertIn("trust_tree", details["2"])
        self.assertIsInstance(details["1"]["topk"][0], dict)
        self.assertIsInstance(details["2"]["topk"][0], dict)


if __name__ == "__main__":
    unittest.main()

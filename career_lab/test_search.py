"""Verify selection and holdout accounting without running native games."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .search import search


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {"managed": [{"club_name": "Fictional Club"}], "source_sha256": "fictional"}
        self.designs = [{"path": f"D{i:02}.fmf"} for i in range(1, 11)]
        self.opponents = [{"club_uid": i, "tactic": "opponent.fmf"} for i in range(5)]

    def test_final_ranking_uses_only_fresh_seed_validation(self):
        calls = []
        screening = [{"path": d["path"], "wins": 40} for d in reversed(self.designs)]
        validation = [{"path": "reference.fmf", "wins": 35}]

        def compare(snapshot, candidates, opponents, output, **kwargs):
            calls.append((list(candidates), list(kwargs["seeds"]), kwargs["ranking_metric"]))
            kwargs["progress"]({"completed": 500})
            return {"matches": 500, "ranking": screening if len(calls) == 1 else validation}

        with tempfile.TemporaryDirectory() as temp, patch("career_lab.search.compare", side_effect=compare):
            output = Path(temp)/"experiment"
            result = search(self.snapshot, self.designs, self.opponents, "reference.fmf", output)
            state = json.loads((output/"state.json").read_text(encoding="utf-8"))
            self.assertEqual(calls[1][0], [d["path"] for d in screening[:4]] + ["reference.fmf"])
            self.assertFalse(set(calls[0][1]) & set(calls[1][1]))
            self.assertEqual([c[2] for c in calls], ["win_rate", "win_rate"])
            self.assertEqual(result["ranking"], validation)
            self.assertEqual(result["screening_ranking"], screening)
            self.assertEqual(result["matches"], 1000)
            self.assertEqual((state["status"], state["completed"], state["total"]), ("completed", 1000, 1000))
            with self.assertRaises(ValueError):
                search(self.snapshot, self.designs, self.opponents, "reference.fmf", output)

    def test_failed_screening_stops_without_publishing_final_results(self):
        with tempfile.TemporaryDirectory() as temp, patch("career_lab.search.compare", side_effect=RuntimeError("native failure")) as compare:
            output = Path(temp)/"experiment"
            with self.assertRaises(RuntimeError):
                search(self.snapshot, self.designs, self.opponents, "reference.fmf", output)
            self.assertEqual(compare.call_count, 1)
            state = json.loads((output/"state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "error")
            self.assertFalse((output/"results.json").exists())


if __name__ == "__main__":
    unittest.main()

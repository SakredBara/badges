import json
import tempfile
import unittest
from pathlib import Path

from wall_compliments import COMPLIMENTS, load_user_ids, send_pending


class WallComplimentsTests(unittest.TestCase):
    def test_load_user_ids_deduplicates_while_preserving_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "users.json"
            path.write_text("[759, 42, 759]", encoding="utf-8")
            self.assertEqual(load_user_ids(path), [759, 42])

    def test_load_user_ids_rejects_invalid_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "users.json"
            path.write_text('[1, "2"]', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_user_ids(path)

    def test_send_pending_posts_only_once_per_user_and_saves_each_success(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "sent.json"
            calls = []
            sleeps = []
            sent = {10}

            count = send_pending(
                [10, 20, 30], sent, state,
                lambda user_id, content: calls.append((user_id, content)),
                interval=21,
                sleep=sleeps.append,
            )

            self.assertEqual(count, 2)
            self.assertEqual([call[0] for call in calls], [20, 30])
            self.assertTrue(all(call[1] in COMPLIMENTS for call in calls))
            self.assertEqual(sleeps, [21])
            self.assertEqual(json.loads(state.read_text(encoding="utf-8")), [10, 20, 30])

            calls.clear()
            self.assertEqual(send_pending([10, 20, 30], sent, state, lambda *args: calls.append(args), interval=0), 0)
            self.assertEqual(calls, [])

    def test_failed_post_is_not_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "sent.json"

            def fail(_user_id, _content):
                raise RuntimeError("network error")

            with self.assertRaises(RuntimeError):
                send_pending([55], set(), state, fail, interval=0)
            self.assertFalse(state.exists())


if __name__ == "__main__":
    unittest.main()

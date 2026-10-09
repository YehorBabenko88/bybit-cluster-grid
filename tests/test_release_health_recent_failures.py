import unittest

from grid.update_protocol import release_health_ok


class ReleaseHealthTests(unittest.TestCase):
    def heartbeat(self, **changes):
        value = {
            "integrity_ok": True,
            "pressure_state": "NORMAL",
            "db_write_failures": 1,
            "db_write_failures_recent": 0,
            "db_queue_ratio": 0.01,
            "db_spool_ratio": 0.02,
        }
        value.update(changes)
        return value

    def test_old_cumulative_failures_do_not_block_rollout(self):
        self.assertEqual(release_health_ok(self.heartbeat()), (True, None))

    def test_new_write_failures_block_rollout(self):
        self.assertEqual(
            release_health_ok(self.heartbeat(db_write_failures_recent=1)),
            (False, "db_write_failures_recent"),
        )

    def test_integrity_failure_still_blocks(self):
        self.assertEqual(
            release_health_ok(self.heartbeat(integrity_ok=False)),
            (False, "integrity"),
        )

    def test_spool_pressure_still_blocks(self):
        self.assertEqual(
            release_health_ok(self.heartbeat(db_spool_ratio=0.9)),
            (False, "db_spool_pressure"),
        )

    def test_legacy_heartbeat_cannot_promote_canary_without_interval_metric(self):
        heartbeat = self.heartbeat()
        del heartbeat["db_write_failures_recent"]
        self.assertEqual(release_health_ok(heartbeat), (False, "db_write_failures_recent_missing"))

    def test_malformed_interval_metric_rejected(self):
        for value in ("oops", -1, None, float("inf")):
            with self.subTest(value=value):
                self.assertEqual(release_health_ok(self.heartbeat(db_write_failures_recent=value))[0], False)


if __name__ == "__main__":
    unittest.main()

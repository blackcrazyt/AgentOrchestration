"""Tests for deploy migration gate (bounty #2823)."""

import unittest
from src.deploy.manager import DeployManager, Migration, MigrationStatus


class TestDeployMigrationGate(unittest.TestCase):

    def setUp(self):
        self.mgr = DeployManager()

    def test_all_migrations_succeed_rollout_allowed(self):
        """When all migrations succeed, rollout is allowed."""
        self.mgr.add_migration(Migration("add_users_table", "CREATE TABLE users", "DROP TABLE users"))
        self.mgr.add_migration(Migration("add_index", "CREATE INDEX", "DROP INDEX"))
        self.assertTrue(self.mgr.run_migrations())
        self.assertTrue(self.mgr.is_rollout_allowed())

    def test_migration_failure_blocks_rollout(self):
        """A failed migration blocks application rollout."""
        self.mgr.add_migration(Migration("m1", "SELECT 1"))
        self.mgr.add_migration(Migration("m2", "CAUSE ERROR IN DB", ""))
        self.mgr.add_migration(Migration("m3", "SELECT 2"))
        self.assertFalse(self.mgr.run_migrations())
        self.assertFalse(self.mgr.is_rollout_allowed())

    def test_pending_migrations_remain_after_failure(self):
        """Migrations after a failure remain PENDING."""
        self.mgr.add_migration(Migration("m1", "SELECT 1"))
        self.mgr.add_migration(Migration("m2", "ERROR QUERY", "ROLLBACK"))
        self.mgr.add_migration(Migration("m3", "SELECT 3"))
        self.mgr.run_migrations()
        pending = self.mgr.get_pending_migrations()
        self.assertIn("m3", pending)

    def test_backward_compatible_migration_rolls_back(self):
        """Failed backward-compatible migration rolls back."""
        m = Migration("add_table", "ERROR SQL", "DROP TABLE IF EXISTS")
        self.mgr.add_migration(m)
        self.mgr.run_migrations()
        self.assertEqual(m.status, MigrationStatus.ROLLED_BACK)

    def test_non_backward_compatible_fails_in_place(self):
        """Non-backward-compatible migration stays FAILED."""
        m = Migration("unsafe", "ERROR SQL", "")
        self.mgr.add_migration(m)
        self.mgr.run_migrations()
        self.assertEqual(m.status, MigrationStatus.FAILED)

    def test_block_reason_recorded(self):
        """Deploy manager records why rollout is blocked."""
        self.mgr.add_migration(Migration("fail", "ERROR"))
        self.mgr.run_migrations()
        reason = self.mgr.get_block_reason()
        self.assertIsNotNone(reason)
        self.assertIn("fail", reason)

    def test_no_migrations_rollout_allowed(self):
        """With no migrations, rollout is allowed."""
        self.assertTrue(self.mgr.is_rollout_allowed())

    def test_migration_status_report(self):
        """get_migration_status returns structured status for all migrations."""
        self.mgr.add_migration(Migration("m1", "SELECT 1"))
        self.mgr.add_migration(Migration("m2", "SELECT 2", "ROLLBACK"))
        self.mgr.run_migrations()
        status = self.mgr.get_migration_status()
        self.assertEqual(len(status), 2)
        self.assertEqual(status[0]["status"], "succeeded")
        self.assertTrue(status[1]["backward_compatible"])


if __name__ == "__main__":
    unittest.main()

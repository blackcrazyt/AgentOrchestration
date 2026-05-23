"""Tests for job lease TTL extension (#2964)."""

import time
import unittest
from src.storage.lease import LeaseManager, LeaseState


class TestLeaseManager(unittest.TestCase):

    def setUp(self):
        self.mgr = LeaseManager()

    # -- acquire --
    def test_acquire_succeeds_for_new_job(self):
        lease = self.mgr.acquire("job-1", "worker-a")
        self.assertIsNotNone(lease)
        self.assertEqual(lease.job_id, "job-1")
        self.assertEqual(lease.state, LeaseState.ACQUIRED)

    def test_duplicate_acquisition_blocked(self):
        self.mgr.acquire("job-1", "worker-a")
        lease2 = self.mgr.acquire("job-1", "worker-b")
        self.assertIsNone(lease2)
        self.assertEqual(len(self.mgr.get_duplicates_blocked()), 1)

    # -- renew --
    def test_renew_large_upload(self):
        lease = self.mgr.acquire("job-upload", "worker-a", ttl=5)
        result = self.mgr.renew_for_upload("job-upload", 100 * 1024 * 1024)
        self.assertTrue(result)
        self.assertEqual(lease.state, LeaseState.UPLOADING)
        self.assertEqual(lease.renewal_count, 1)

    def test_renew_small_upload_no_renewal_needed(self):
        lease = self.mgr.acquire("job-small", "worker-a", ttl=30)
        self.mgr.renew_for_upload("job-small", 1024)
        self.assertEqual(lease.state, LeaseState.UPLOADING)
        self.assertEqual(lease.renewal_count, 0)

    def test_renew_unknown_job(self):
        self.assertFalse(self.mgr.renew_for_upload("ghost", 100 * 1024 * 1024))

    # -- complete --
    def test_complete_lease(self):
        self.mgr.acquire("job-c", "worker-a")
        self.assertTrue(self.mgr.complete("job-c"))

    def test_complete_unknown_lease(self):
        self.assertFalse(self.mgr.complete("nope"))

    # -- expiry --
    def test_check_expired(self):
        self.mgr.acquire("job-exp", "worker-a", ttl=0)
        time.sleep(0.1)
        expired = self.mgr.check_expired()
        self.assertIn("job-exp", expired)
        self.assertEqual(len(self.mgr.get_expired_leases()), 1)

    # -- renewal count --
    def test_renewal_count(self):
        self.mgr.acquire("job-r", "worker-a", ttl=60)
        self.mgr.renew_for_upload("job-r", 100 * 1024 * 1024)
        self.mgr.renew_for_upload("job-r", 100 * 1024 * 1024)
        self.assertEqual(self.mgr.get_renewal_count("job-r"), 2)


if __name__ == "__main__":
    unittest.main()

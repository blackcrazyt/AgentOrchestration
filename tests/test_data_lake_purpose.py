"""Tests for data lake purpose limitation (bounty #1555)."""

import unittest
from src.data.pipeline import (
    DataClass, DataLake, DestinationPolicy, IngestionManifest,
)


class TestDataLakePurposeLimitation(unittest.TestCase):

    def setUp(self):
        self.lake = DataLake()
        # Register destinations with different policies
        self.lake.register_destination(
            "analytics-warehouse",
            DestinationPolicy([DataClass.ANALYTICAL, DataClass.OPERATIONAL]),
        )
        self.lake.register_destination(
            "audit-store",
            DestinationPolicy([DataClass.AUDIT]),
        )
        self.lake.register_destination(
            "sensitive-vault",
            DestinationPolicy([DataClass.SENSITIVE]),
        )

    # -- accepted writes --
    def test_operational_write_to_analytics_accepted(self):
        """OPERATIONAL data is allowed at analytics-warehouse."""
        manifest = IngestionManifest("daily-metrics", DataClass.OPERATIONAL, "ops-team", "analytics-warehouse")
        self.assertTrue(self.lake.write(manifest))
        self.assertEqual(self.lake.write_count(), 1)

    def test_audit_write_to_audit_store_accepted(self):
        """AUDIT data is allowed at audit-store."""
        manifest = IngestionManifest("access-log", DataClass.AUDIT, "security", "audit-store")
        self.assertTrue(self.lake.write(manifest))

    def test_sensitive_write_to_vault_accepted(self):
        """SENSITIVE data is allowed at sensitive-vault."""
        manifest = IngestionManifest("pii-export", DataClass.SENSITIVE, "compliance", "sensitive-vault")
        self.assertTrue(self.lake.write(manifest))

    # -- rejected writes --
    def test_operational_write_to_audit_store_rejected(self):
        """OPERATIONAL data is NOT allowed at audit-store."""
        manifest = IngestionManifest("ops-log", DataClass.OPERATIONAL, "ops-team", "audit-store")
        self.assertFalse(self.lake.write(manifest))
        self.assertEqual(self.lake.write_count(), 0)
        self.assertEqual(self.lake.rejected_count(), 1)

    def test_sensitive_write_to_analytics_rejected(self):
        """SENSITIVE data is NOT allowed at analytics-warehouse."""
        manifest = IngestionManifest("secret-data", DataClass.SENSITIVE, "compliance", "analytics-warehouse")
        self.assertFalse(self.lake.write(manifest))

    def test_unknown_destination_rejected(self):
        """Writing to an unregistered destination is rejected."""
        manifest = IngestionManifest("data", DataClass.OPERATIONAL, "dev", "unknown-sink")
        self.assertFalse(self.lake.write(manifest))
        self.assertEqual(self.lake.rejected_count(), 1)

    # -- listing and audit --
    def test_list_writes_filtered_by_owner(self):
        """list_writes() can filter by owner."""
        self.lake.write(IngestionManifest("p1", DataClass.ANALYTICAL, "team-a", "analytics-warehouse"))
        self.lake.write(IngestionManifest("p2", DataClass.ANALYTICAL, "team-b", "analytics-warehouse"))
        results = self.lake.list_writes(owner="team-a")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["owner"], "team-a")

    def test_list_writes_filtered_by_purpose(self):
        """list_writes() can filter by purpose."""
        self.lake.write(IngestionManifest("daily", DataClass.ANALYTICAL, "analytics", "analytics-warehouse"))
        self.lake.write(IngestionManifest("weekly", DataClass.ANALYTICAL, "analytics", "analytics-warehouse"))
        results = self.lake.list_writes(purpose="daily")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["purpose"], "daily")

    def test_rejected_entries_include_reason(self):
        """Rejected writes include rejection reason and owner."""
        manifest = IngestionManifest("bad", DataClass.AUDIT, "eng", "analytics-warehouse")
        self.lake.write(manifest)
        rejected = self.lake.list_rejected()
        self.assertEqual(len(rejected), 1)
        self.assertIn("reason", rejected[0])
        self.assertEqual(rejected[0]["owner"], "eng")

    def test_manifest_to_dict_includes_all_fields(self):
        """Manifest.to_dict() includes purpose, data_class, owner, destination."""
        m = IngestionManifest("report", DataClass.ANALYTICAL, "bi-team", "analytics-warehouse", 4096)
        d = m.to_dict()
        self.assertEqual(d["purpose"], "report")
        self.assertEqual(d["data_class"], "analytical")
        self.assertEqual(d["owner"], "bi-team")
        self.assertEqual(d["destination"], "analytics-warehouse")
        self.assertEqual(d["payload_size_bytes"], 4096)


if __name__ == "__main__":
    unittest.main()

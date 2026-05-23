"""Tests for artifact retention policy validation (bounty #2544)."""

import unittest
from src.orchestrator.workflow import RetentionPolicy, ArtifactValidator


class TestRetentionPolicy(unittest.TestCase):

    def setUp(self):
        self.policy = RetentionPolicy(max_age_days=30, max_count=1000)

    def test_valid_artifact_accepted(self):
        """Compliant artifact passes validation."""
        self.assertTrue(self.policy.validate("log", 15, 500))

    def test_unknown_type_rejected(self):
        """Disallowed artifact type fails validation."""
        self.assertFalse(self.policy.validate("malware", 1, 1))

    def test_age_exceeds_max_rejected(self):
        """Artifact older than max_age_days is rejected."""
        self.assertFalse(self.policy.validate("log", 45, 100))

    def test_count_exceeds_max_rejected(self):
        """Count exceeding max_count is rejected."""
        self.assertFalse(self.policy.validate("report", 5, 1500))

    def test_policy_to_dict(self):
        """to_dict() serializes policy settings."""
        d = self.policy.to_dict()
        self.assertEqual(d["max_age_days"], 30)
        self.assertEqual(d["max_count"], 1000)
        self.assertIn("log", d["allowed_types"])

    def test_default_allowed_types(self):
        """Default policy includes log, artifact, trace, report."""
        self.assertIn("trace", self.policy.allowed_types)
        self.assertIn("report", self.policy.allowed_types)


class TestArtifactValidator(unittest.TestCase):

    def setUp(self):
        self.validator = ArtifactValidator()

    def test_validate_artifact_returns_true(self):
        """Valid artifact returns True."""
        self.assertTrue(self.validator.validate_artifact("log", 10, 100))

    def test_validate_artifact_returns_false(self):
        """Invalid artifact returns False."""
        self.assertFalse(self.validator.validate_artifact("bad", 100, 5000))

    def test_violations_recorded(self):
        """Violations are accumulated for audit."""
        self.validator.validate_artifact("bad-type", 1, 1)
        self.validator.validate_artifact("log", 999, 1)
        violations = self.validator.get_violations()
        self.assertEqual(len(violations), 2)

    def test_violation_reason_includes_details(self):
        """Violation reasons explain which constraint was breached."""
        self.validator.validate_artifact("trace", 99, 1)
        v = self.validator.get_violations()
        self.assertIn("age", v[0]["reason"])
        self.assertIn("99", v[0]["reason"])


if __name__ == "__main__":
    unittest.main()

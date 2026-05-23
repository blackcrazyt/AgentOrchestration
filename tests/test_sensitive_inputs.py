"""Tests for sensitive input declarations in workflow (bounty #2457)."""

import unittest
from src.orchestrator.workflow import SensitiveInput, InputSchemaValidator


class TestSensitiveInput(unittest.TestCase):

    def test_valid_scope_accepted(self):
        """Scopes in VALID_SCOPES are accepted."""
        si = SensitiveInput("api_token", "token")
        self.assertEqual(si.name, "api_token")
        self.assertEqual(si.scope, "token")

    def test_invalid_scope_raises(self):
        """Invalid scope raises ValueError."""
        with self.assertRaises(ValueError):
            SensitiveInput("bad", "not_a_scope")

    def test_to_dict(self):
        """to_dict serializes name, scope, default."""
        si = SensitiveInput("db_password", "secret", default="***")
        d = si.to_dict()
        self.assertEqual(d["name"], "db_password")
        self.assertEqual(d["scope"], "secret")
        self.assertEqual(d["default"], "***")


class TestInputSchemaValidator(unittest.TestCase):

    def setUp(self):
        self.validator = InputSchemaValidator([
            SensitiveInput("api_token", "token"),
            SensitiveInput("db_secret", "secret"),
        ])

    def test_declared_inputs_pass(self):
        """Inputs matching declared sensitive keys pass validation."""
        inputs = {"api_token": "abc123", "db_secret": "xyz789", "name": "job-1"}
        self.assertTrue(self.validator.validate(inputs))

    def test_undeclared_sensitive_input_rejected(self):
        """Token-like key not in declared list is rejected."""
        inputs = {"api_token": "abc", "ssh_key": "secret-key-data"}
        self.assertFalse(self.validator.validate(inputs))

    def test_violations_recorded(self):
        """Each undeclared sensitive key generates a violation."""
        self.validator.validate({
            "api_token": "ok",
            "stripe_secret": "sk_live_xxx",
            "user_password": "1234",
        })
        v = self.validator.get_violations()
        self.assertEqual(len(v), 2)

    def test_violation_includes_key_and_reason(self):
        """Violation entries include key and reason."""
        self.validator.validate({"aws_key": "AKIA..."})
        v = self.validator.get_violations()
        self.assertEqual(v[0]["key"], "aws_key")
        self.assertIn("Undeclared", v[0]["reason"])

    def test_no_sensitive_inputs_passes(self):
        """Plain inputs without sensitive patterns pass."""
        self.assertTrue(self.validator.validate({"name": "task-1", "count": 5}))

    def test_declare_adds_new_input(self):
        """declare() adds a sensitive input dynamically."""
        self.validator.declare(SensitiveInput("new_token", "token"))
        self.assertTrue(self.validator.validate({"new_token": "t"}))

    def test_case_insensitive_matching(self):
        """Sensitive pattern matching is case-insensitive."""
        v2 = InputSchemaValidator()
        v2.declare(SensitiveInput("API_TOKEN", "token"))
        self.assertTrue(v2.validate({"api_token": "x"}))


if __name__ == "__main__":
    unittest.main()

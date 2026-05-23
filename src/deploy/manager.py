"""Deployment manager with migration gate before application rollout (bounty #2823).

Migrations must complete and pass compatibility checks before new application
pods receive traffic.  Migration failures stop the rollout and keep the prior
version serving.
"""

from enum import Enum
from typing import Dict, List, Optional


class MigrationStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class Migration:
    def __init__(self, name: str, forward_sql: str, backward_sql: str = ""):
        self.name = name
        self.forward_sql = forward_sql
        self.backward_sql = backward_sql
        self.status = MigrationStatus.PENDING
        self.error: Optional[str] = None

    def is_backward_compatible(self) -> bool:
        """A migration is backward-compatible if it has a rollback script."""
        return bool(self.backward_sql.strip())


class DeployManager:
    def __init__(self):
        self._migrations: List[Migration] = []
        self._rollout_blocked = False
        self._block_reason: Optional[str] = None

    def add_migration(self, migration: Migration) -> None:
        self._migrations.append(migration)

    def run_migrations(self) -> bool:
        """Run all pending migrations in order. Returns True if all succeed.

        If any migration fails, the sequence stops and remaining migrations
        remain PENDING.  Failed migrations with backward SQL are rolled back.
        """
        for m in self._migrations:
            if m.status != MigrationStatus.PENDING:
                continue
            m.status = MigrationStatus.RUNNING
            try:
                self._execute_sql(m.forward_sql)
                m.status = MigrationStatus.SUCCEEDED
            except Exception as e:
                m.error = str(e)
                m.status = MigrationStatus.FAILED
                self._rollout_blocked = True
                self._block_reason = f"Migration '{m.name}' failed: {e}"
                # Rollback failed migration if possible
                if m.is_backward_compatible():
                    try:
                        self._execute_sql(m.backward_sql)
                        m.status = MigrationStatus.ROLLED_BACK
                    except Exception:
                        pass
                return False
        return True

    def is_rollout_allowed(self) -> bool:
        """Check if application rollout can proceed."""
        if self._rollout_blocked:
            return False
        # All migrations must be in a terminal non-failed state
        for m in self._migrations:
            if m.status in (MigrationStatus.PENDING, MigrationStatus.RUNNING, MigrationStatus.FAILED):
                return False
        return True

    def get_block_reason(self) -> Optional[str]:
        return self._block_reason

    def get_migration_status(self) -> List[Dict]:
        return [
            {
                "name": m.name,
                "status": m.status.value,
                "backward_compatible": m.is_backward_compatible(),
                "error": m.error,
            }
            for m in self._migrations
        ]

    def get_pending_migrations(self) -> List[str]:
        return [m.name for m in self._migrations if m.status == MigrationStatus.PENDING]

    def _execute_sql(self, sql: str) -> None:
        """Simulate SQL execution. Raises if SQL contains 'ERROR'."""
        if "ERROR" in sql.upper():
            raise RuntimeError(f"SQL execution failed: intentional error in migration")

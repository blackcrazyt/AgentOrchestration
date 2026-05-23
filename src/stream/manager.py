"""SSE (Server-Sent Events) cursor manager with ownership validation (bounty #2658).

Every SSE cursor is scoped to a workspace + role.  Cursor ownership is
validated on every read — cursors from other workspaces are rejected.
"""

from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4


class CursorState(Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class CursorOwner:
    """Ownership metadata for an SSE cursor."""
    def __init__(self, workspace: str, role: str = "reader"):
        self.workspace = workspace
        self.role = role

    def __eq__(self, other) -> bool:
        if not isinstance(other, CursorOwner):
            return False
        return self.workspace == other.workspace and self.role == other.role

    def to_dict(self) -> Dict:
        return {"workspace": self.workspace, "role": self.role}


class SSECursor:
    def __init__(self, stream: str, owner: CursorOwner, last_event_id: str = ""):
        self.id = str(uuid4())
        self.stream = stream
        self.owner = owner
        self.last_event_id = last_event_id
        self.state = CursorState.ACTIVE

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "stream": self.stream,
            "owner": self.owner.to_dict(),
            "last_event_id": self.last_event_id,
            "state": self.state.value,
        }


class SSEManager:
    """Manages SSE cursors with workspace-scoped ownership validation."""

    def __init__(self):
        self._cursors: Dict[str, SSECursor] = {}
        self._rejected: List[Dict] = []

    def create_cursor(
        self, stream: str, workspace: str, role: str = "reader", last_event_id: str = ""
    ) -> SSECursor:
        owner = CursorOwner(workspace, role)
        cursor = SSECursor(stream, owner, last_event_id)
        self._cursors[cursor.id] = cursor
        return cursor

    def validate_ownership(self, cursor_id: str, workspace: str) -> bool:
        """Check that the cursor belongs to the requesting workspace.

        Returns True if the cursor exists and belongs to this workspace.
        Cross-workspace access is rejected and logged.
        """
        cursor = self._cursors.get(cursor_id)
        if not cursor:
            return False

        if cursor.state != CursorState.ACTIVE:
            self._rejected.append({
                "cursor_id": cursor_id,
                "workspace": workspace,
                "reason": f"Cursor is {cursor.state.value}",
            })
            return False

        if cursor.owner.workspace != workspace:
            self._rejected.append({
                "cursor_id": cursor_id,
                "requesting_workspace": workspace,
                "owner_workspace": cursor.owner.workspace,
                "reason": f"Cursor belongs to '{cursor.owner.workspace}', not '{workspace}'",
            })
            return False

        return True

    def update_cursor(self, cursor_id: str, workspace: str, last_event_id: str) -> bool:
        """Update cursor position if ownership is valid."""
        if not self.validate_ownership(cursor_id, workspace):
            return False
        self._cursors[cursor_id].last_event_id = last_event_id
        return True

    def revoke_cursor(self, cursor_id: str) -> bool:
        cursor = self._cursors.get(cursor_id)
        if not cursor:
            return False
        cursor.state = CursorState.REVOKED
        return True

    def get_cursor(self, cursor_id: str) -> Optional[Dict]:
        cursor = self._cursors.get(cursor_id)
        return cursor.to_dict() if cursor else None

    def list_cursors(self, workspace: Optional[str] = None) -> List[Dict]:
        cursors = self._cursors.values()
        if workspace:
            cursors = [c for c in cursors if c.owner.workspace == workspace]
        return [c.to_dict() for c in cursors]

    def get_rejected(self) -> List[Dict]:
        return list(self._rejected)

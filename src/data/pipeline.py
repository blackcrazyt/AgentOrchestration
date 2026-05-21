"""Data Lake Pipeline — Governed ingestion with purpose limitation (bounty #1555).

Every data lake write requires purpose, data_class, owner, and approved destination.
Writes are blocked when the destination policy does not approve the data class.
"""

from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4


class DataClass(Enum):
    OPERATIONAL = "operational"
    ANALYTICAL = "analytical"
    SENSITIVE = "sensitive"
    AUDIT = "audit"


class DestinationPolicy:
    """Governs which data classes are allowed at a destination."""

    def __init__(self, allowed_classes: List[DataClass]):
        self.allowed_classes = set(allowed_classes)

    def allows(self, data_class: DataClass) -> bool:
        return data_class in self.allowed_classes


class IngestionManifest:
    """Metadata required for every data lake write."""

    def __init__(
        self,
        purpose: str,
        data_class: DataClass,
        owner: str,
        destination: str,
        payload_size_bytes: int = 0,
    ):
        self.id = str(uuid4())
        self.purpose = purpose
        self.data_class = data_class
        self.owner = owner
        self.destination = destination
        self.payload_size_bytes = payload_size_bytes

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "purpose": self.purpose,
            "data_class": self.data_class.value,
            "owner": self.owner,
            "destination": self.destination,
            "payload_size_bytes": self.payload_size_bytes,
        }


class DataLake:
    """Governed data lake with purpose-based write validation."""

    def __init__(self):
        self._destinations: Dict[str, DestinationPolicy] = {}
        self._writes: List[IngestionManifest] = []
        self._rejected: List[Dict] = []

    def register_destination(self, name: str, policy: DestinationPolicy) -> None:
        """Register a destination with its allowed data classes."""
        self._destinations[name] = policy

    def write(self, manifest: IngestionManifest) -> bool:
        """Attempt a governed write. Returns True if accepted, False if rejected.

        Rejection happens when:
        - The destination is not registered.
        - The destination policy does not allow the data class.
        """
        dest = manifest.destination
        if dest not in self._destinations:
            self._rejected.append({
                "manifest_id": manifest.id,
                "reason": f"Unknown destination: {dest}",
                "owner": manifest.owner,
            })
            return False

        policy = self._destinations[dest]
        if not policy.allows(manifest.data_class):
            self._rejected.append({
                "manifest_id": manifest.id,
                "reason": (
                    f"Data class '{manifest.data_class.value}' not allowed "
                    f"at destination '{dest}'"
                ),
                "owner": manifest.owner,
            })
            return False

        self._writes.append(manifest)
        return True

    def list_writes(self, owner: Optional[str] = None, purpose: Optional[str] = None) -> List[Dict]:
        """List accepted writes, optionally filtered by owner or purpose."""
        results = self._writes
        if owner:
            results = [w for w in results if w.owner == owner]
        if purpose:
            results = [w for w in results if w.purpose == purpose]
        return [w.to_dict() for w in results]

    def list_rejected(self) -> List[Dict]:
        """Return all rejected writes for audit."""
        return list(self._rejected)

    def write_count(self) -> int:
        return len(self._writes)

    def rejected_count(self) -> int:
        return len(self._rejected)

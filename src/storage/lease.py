"""Job lease manager with TTL extension for large artifact uploads (bounty #2964).

Workers renew leases during long uploads to prevent duplicate task execution
when the lease expires before artifact upload completes.
"""

import time
from enum import Enum
from typing import Dict, List, Optional


class LeaseState(Enum):
    ACQUIRED = "acquired"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    EXPIRED = "expired"


class JobLease:
    def __init__(self, job_id: str, worker_id: str, ttl_seconds: int = 30):
        self.job_id = job_id
        self.worker_id = worker_id
        self.ttl_seconds = ttl_seconds
        self.state = LeaseState.ACQUIRED
        self.acquired_at = time.time()
        self.expires_at = self.acquired_at + ttl_seconds
        self.renewal_count = 0

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def renew(self) -> bool:
        """Extend the lease by ttl_seconds. Returns False if already expired."""
        if self.is_expired():
            self.state = LeaseState.EXPIRED
            return False
        self.expires_at = time.time() + self.ttl_seconds
        self.renewal_count += 1
        return True

    def start_upload(self) -> None:
        self.state = LeaseState.UPLOADING


class LeaseManager:
    """Manages job leases with TTL extension for large artifact uploads."""

    DEFAULT_TTL = 30  # seconds
    LARGE_UPLOAD_THRESHOLD = 50 * 1024 * 1024  # 50 MB

    def __init__(self):
        self._leases: Dict[str, JobLease] = {}
        self._expired: List[Dict] = []
        self._duplicates: List[Dict] = []

    def acquire(self, job_id: str, worker_id: str, ttl: int = None) -> Optional[JobLease]:
        """Acquire a lease for job execution. Returns None if already acquired."""
        existing = self._leases.get(job_id)
        if existing and not existing.is_expired():
            self._duplicates.append({
                "job_id": job_id, "worker_id": worker_id,
                "existing_worker": existing.worker_id,
                "reason": "Duplicate acquisition blocked",
            })
            return None
        lease = JobLease(job_id, worker_id, ttl or self.DEFAULT_TTL)
        self._leases[job_id] = lease
        return lease

    def renew_for_upload(self, job_id: str, upload_size_bytes: int) -> bool:
        """Renew lease when uploading large artifacts. Returns False if expired."""
        lease = self._leases.get(job_id)
        if not lease:
            return False
        if lease.state == LeaseState.EXPIRED:
            return False
        lease.start_upload()
        if upload_size_bytes >= self.LARGE_UPLOAD_THRESHOLD:
            return lease.renew()
        return True

    def complete(self, job_id: str) -> bool:
        """Mark a lease as completed."""
        lease = self._leases.get(job_id)
        if not lease:
            return False
        lease.state = LeaseState.COMPLETED
        return True

    def check_expired(self) -> List[str]:
        """Return list of expired job_ids and mark them EXPIRED."""
        expired = []
        for job_id, lease in self._leases.items():
            if lease.is_expired() and lease.state != LeaseState.EXPIRED:
                lease.state = LeaseState.EXPIRED
                self._expired.append({
                    "job_id": job_id, "worker_id": lease.worker_id,
                    "reason": "Lease expired",
                })
                expired.append(job_id)
        return expired

    def get_expired_leases(self) -> List[Dict]:
        return list(self._expired)

    def get_duplicates_blocked(self) -> List[Dict]:
        return list(self._duplicates)

    def get_renewal_count(self, job_id: str) -> int:
        lease = self._leases.get(job_id)
        return lease.renewal_count if lease else 0

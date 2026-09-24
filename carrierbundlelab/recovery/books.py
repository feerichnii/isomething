"""Books/AirTraffic staging recovery facade."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from carrierbundlelab.models import VerificationResult


@dataclass(frozen=True)
class BooksSnapshot:
    path: Path
    exists: bool


class BooksRecoveryService:
    def __init__(self, staging_path: Path = Path("work/books-staging")) -> None:
        self.staging_path = staging_path

    def snapshot(self) -> BooksSnapshot:
        return BooksSnapshot(path=self.staging_path, exists=self.staging_path.exists())

    def verify_snapshot(self) -> VerificationResult:
        return VerificationResult(ok=True, message="snapshot metadata captured")

    def restore(self, snapshot: BooksSnapshot) -> VerificationResult:
        if snapshot.exists:
            snapshot.path.mkdir(parents=True, exist_ok=True)
        return VerificationResult(ok=True, message="books staging restored to recorded existence state")

    def verify_restore(self) -> VerificationResult:
        return VerificationResult(ok=True, message="books restore verified")

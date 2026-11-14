from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent_crossbar.security.errors import (
    SecurityReviewNotFoundError,
    SecurityWaiverNotFoundError,
)
from agent_crossbar.storage.database import Database


@dataclass(frozen=True, slots=True)
class SecurityReviewRecord:
    review_id: str
    created_at: datetime
    root: str
    base: str | None
    staged: bool
    verdict: str
    policy_name: str
    run_id: str | None
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SecurityWaiverRecord:
    waiver_id: str
    rule_id: str
    file_pattern: str
    owner: str
    reason: str
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None


class SecurityStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    def save_review(
        self,
        *,
        root: str,
        base: str | None,
        staged: bool,
        verdict: str,
        policy_name: str,
        run_id: str | None,
        payload: dict[str, Any],
    ) -> SecurityReviewRecord:
        review_id = f"rev_{uuid.uuid4().hex}"
        created_at = datetime.now(timezone.utc)
        with self._database.write_lock, self._database.connection:
            self._database.connection.execute(
                """
                INSERT INTO security_reviews(
                    review_id, created_at, root, base, staged, verdict,
                    policy_name, run_id, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    created_at.isoformat(),
                    root,
                    base,
                    1 if staged else 0,
                    verdict,
                    policy_name,
                    run_id,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            )
        return self.get_review(review_id)

    def get_review(self, review_id: str) -> SecurityReviewRecord:
        row = self._database.connection.execute(
            "SELECT * FROM security_reviews WHERE review_id = ?",
            (review_id,),
        ).fetchone()
        if row is None:
            raise SecurityReviewNotFoundError(f"security review {review_id} does not exist")
        return _review_from_row(row)

    def update_payload(self, review_id: str, payload: dict[str, Any]) -> None:
        with self._database.write_lock, self._database.connection:
            self._database.connection.execute(
                "UPDATE security_reviews SET payload_json = ? WHERE review_id = ?",
                (
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    review_id,
                ),
            )

    def list_reviews(self, *, limit: int = 50) -> list[SecurityReviewRecord]:
        rows = self._database.connection.execute(
            """
            SELECT * FROM security_reviews
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(limit, 200)),),
        ).fetchall()
        return [_review_from_row(row) for row in rows]

    def create_waiver(
        self,
        *,
        rule_id: str,
        file_pattern: str,
        owner: str,
        reason: str,
        expires_at: datetime,
    ) -> SecurityWaiverRecord:
        waiver_id = f"wv_{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc)
        with self._database.write_lock, self._database.connection:
            self._database.connection.execute(
                """
                INSERT INTO security_waivers(
                    waiver_id, rule_id, file_pattern, owner, reason,
                    expires_at, created_at, revoked_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    waiver_id,
                    rule_id,
                    file_pattern,
                    owner,
                    reason,
                    _utc(expires_at).isoformat(),
                    now.isoformat(),
                ),
            )
        return self.get_waiver(waiver_id)

    def get_waiver(self, waiver_id: str) -> SecurityWaiverRecord:
        row = self._database.connection.execute(
            "SELECT * FROM security_waivers WHERE waiver_id = ?",
            (waiver_id,),
        ).fetchone()
        if row is None:
            raise SecurityWaiverNotFoundError(f"security waiver {waiver_id} does not exist")
        return _waiver_from_row(row)

    def list_waivers(self) -> list[SecurityWaiverRecord]:
        rows = self._database.connection.execute(
            "SELECT * FROM security_waivers ORDER BY created_at DESC"
        ).fetchall()
        return [_waiver_from_row(row) for row in rows]

    def active_waivers(self, now: datetime | None = None) -> list[dict[str, Any]]:
        current = _utc(now or datetime.now(timezone.utc))
        return [
            {
                "waiver_id": waiver.waiver_id,
                "rule_id": waiver.rule_id,
                "file_pattern": waiver.file_pattern,
                "owner": waiver.owner,
                "reason": waiver.reason,
                "expires_at": waiver.expires_at.isoformat(),
            }
            for waiver in self.list_waivers()
            if waiver.revoked_at is None and waiver.expires_at > current
        ]

    def revoke_waiver(self, waiver_id: str) -> SecurityWaiverRecord:
        now = datetime.now(timezone.utc).isoformat()
        with self._database.write_lock, self._database.connection:
            cursor = self._database.connection.execute(
                """
                UPDATE security_waivers SET revoked_at = ?
                WHERE waiver_id = ? AND revoked_at IS NULL
                """,
                (now, waiver_id),
            )
        if cursor.rowcount != 1:
            self.get_waiver(waiver_id)
            raise SecurityWaiverNotFoundError(
                f"security waiver {waiver_id} is already revoked"
            )
        return self.get_waiver(waiver_id)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _review_from_row(row: sqlite3.Row) -> SecurityReviewRecord:
    return SecurityReviewRecord(
        review_id=row["review_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        root=row["root"],
        base=row["base"],
        staged=bool(row["staged"]),
        verdict=row["verdict"],
        policy_name=row["policy_name"],
        run_id=row["run_id"],
        payload=json.loads(row["payload_json"]),
    )


def _waiver_from_row(row: sqlite3.Row) -> SecurityWaiverRecord:
    return SecurityWaiverRecord(
        waiver_id=row["waiver_id"],
        rule_id=row["rule_id"],
        file_pattern=row["file_pattern"],
        owner=row["owner"],
        reason=row["reason"],
        expires_at=datetime.fromisoformat(row["expires_at"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        revoked_at=(
            datetime.fromisoformat(row["revoked_at"])
            if row["revoked_at"] is not None
            else None
        ),
    )

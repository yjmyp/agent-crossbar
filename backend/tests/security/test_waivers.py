from datetime import datetime, timedelta, timezone

from agent_crossbar.security.policy import waiver_applies


def test_waiver_requires_future_expiry_and_matching_scope() -> None:
    now = datetime.now(timezone.utc)
    finding = {"rule_id": "CS-PY-001", "file": "app/handler.py", "line": 12}
    active = {
        "rule_id": "*",
        "file_pattern": "app/*.py",
        "owner": "security-lead",
        "expires_at": (now + timedelta(days=1)).isoformat(),
    }
    assert waiver_applies(active, finding, now) is True

    expired = {**active, "expires_at": (now - timedelta(seconds=1)).isoformat()}
    assert waiver_applies(expired, finding, now) is False

    wrong_rule = {**active, "rule_id": "CS-JS-001"}
    assert waiver_applies(wrong_rule, finding, now) is False

    wrong_file = {**active, "file_pattern": "scripts/*.py"}
    assert waiver_applies(wrong_file, finding, now) is False


def test_waiver_with_invalid_timestamp_is_not_applied() -> None:
    now = datetime.now(timezone.utc)
    finding = {"rule_id": "CS-PY-001", "file": "handler.py"}
    assert waiver_applies({"rule_id": "*", "expires_at": "not-a-date"}, finding, now) is False

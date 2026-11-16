from __future__ import annotations

from agent_crossbar.security.engine.rules import scan_generic_text, scan_text


def test_regexp_exec_is_not_child_process_exec() -> None:
    findings = scan_generic_text("app.ts", "const match = /x/.exec(value);\n")
    assert [item.rule_id for item in findings] == []


def test_child_process_exec_is_still_flagged() -> None:
    findings = scan_generic_text("app.ts", "cp.exec(userInput);\n")
    assert [item.rule_id for item in findings] == ["CS-JS-002"]


def test_eval_inside_string_or_comment_is_not_flagged() -> None:
    findings = scan_generic_text(
        "fake.ts",
        'const evidence = "eval(request.args[\\"expr\\"])"; // eval(userInput)\n',
    )
    assert [item.rule_id for item in findings] == []
    assert [item.rule_id for item in scan_generic_text("app.ts", "eval(userInput);\n")] == [
        "CS-JS-001"
    ]


def test_descriptive_secret_placeholders_are_not_high_entropy() -> None:
    assert scan_text("example.py", 'api_key = "must-not-leak"\n') == []
    assert scan_text("example.py", 'api_key = "demo-local-token"\n') == []
    secret = "".join(["aB3xK9mQ", "7pR2tV8w", "Z4nL6cD1", "fG5hJ0s"])
    real = f'api_key = "{secret}"\n'
    assert [item.rule_id for item in scan_text("example.py", real)] == ["CS-SECRET-009"]

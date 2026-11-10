import pytest
from agent_crossbar.domain.spec import (
    AgentSpec,
    CollaborationPolicy,
    ExecutionPolicy,
    ToolReference,
)
from pydantic import ValidationError


def make_spec(**overrides: object) -> AgentSpec:
    values: dict[str, object] = {
        "name": "Researcher",
        "version": "0.1.0",
        "instructions": "Find facts and cite sources.",
    }
    values.update(overrides)
    return AgentSpec(**values)


def test_rejects_blank_agent_name() -> None:
    with pytest.raises(ValidationError):
        make_spec(name=" ")


@pytest.mark.parametrize("version", ["1", "1.2", "v1.2.3", "1.2.3.4", "01.2.3"])
def test_rejects_non_semantic_versions(version: str) -> None:
    with pytest.raises(ValidationError):
        make_spec(version=version)


@pytest.mark.parametrize("version", ["1.0.0", "2.14.7", "1.0.0-rc.1"])
def test_accepts_semantic_versions(version: str) -> None:
    assert make_spec(version=version).version == version


def test_digest_is_stable_for_equivalent_specs() -> None:
    first = make_spec(
        output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
        }
    )
    second = make_spec(
        output_schema={
            "properties": {"answer": {"type": "string"}},
            "type": "object",
        }
    )

    assert first.digest() == second.digest()


def test_digest_changes_when_behavior_changes() -> None:
    first = make_spec(instructions="Find primary sources.")
    second = make_spec(instructions="Find secondary sources.")

    assert first.digest() != second.digest()


def test_digest_has_stable_sha256_format() -> None:
    digest = make_spec().digest()

    assert digest == "sha256:cb9741275e1e7106da951e821a4848d8b5bf6787b37e81e0954bb206b3297c4e"


def test_applies_safe_execution_defaults() -> None:
    spec = make_spec()

    assert spec.execution == ExecutionPolicy(
        max_turns=12,
        timeout_seconds=300,
        retry_count=1,
        max_concurrency=1,
    )
    assert spec.collaboration == CollaborationPolicy(mode="single", max_agents=1)


def test_rejects_duplicate_tool_references() -> None:
    with pytest.raises(ValidationError, match="unique"):
        make_spec(
            tools=[
                ToolReference(name="search.web"),
                ToolReference(name="search.web"),
            ]
        )


def test_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AgentSpec(
            name="Researcher",
            version="0.1.0",
            instructions="Find facts.",
            api_key="must-not-be-here",
        )


@pytest.mark.parametrize("mode", ["handoff", "group"])
def test_rejects_collaboration_modes_without_distinct_runtime_semantics(
    mode: str,
) -> None:
    with pytest.raises(ValidationError):
        CollaborationPolicy(mode=mode, max_agents=2)


def test_round_trips_through_canonical_json() -> None:
    original = make_spec(evaluation_tags=["research", "grounded"])

    restored = AgentSpec.model_validate_json(original.model_dump_json())

    assert restored == original
    assert restored.digest() == original.digest()

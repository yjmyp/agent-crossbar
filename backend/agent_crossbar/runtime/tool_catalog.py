from __future__ import annotations

import json

from agent_crossbar.runtime.mcp_client import MCPClientService
from agent_crossbar.runtime.tools import (
    ToolDefinition,
    ToolExecutionError,
    ToolExecutor,
    ToolRegistry,
    default_tool_definitions,
    default_tool_executors,
)
from agent_crossbar.storage.knowledge import KnowledgeStore


class RuntimeToolCatalog:
    def __init__(
        self,
        knowledge_store: KnowledgeStore,
        mcp_service: MCPClientService,
    ) -> None:
        self._knowledge_store = knowledge_store
        self._mcp_service = mcp_service

    def available(self) -> list[ToolDefinition]:
        return [
            *default_tool_definitions(),
            self._knowledge_definition(),
            *self._mcp_service.definitions(),
        ]

    def registry(self) -> ToolRegistry:
        definitions = self.available()
        executors: dict[str, ToolExecutor] = default_tool_executors()
        executors["knowledge_search"] = self._search_knowledge
        for definition in definitions:
            if definition.name.startswith("mcp."):
                executors[definition.name] = self._mcp_executor(definition.name)
        return ToolRegistry(definitions=definitions, executors=executors)

    def validate_names(self, names: tuple[str, ...]) -> None:
        definitions = {definition.name for definition in self.available()}
        missing = [name for name in names if name not in definitions]
        if missing:
            joined = ", ".join(repr(name) for name in missing)
            raise ToolExecutionError(
                "tool_not_available",
                f"tools are not available or enabled: {joined}",
            )

    async def _search_knowledge(self, arguments: dict[str, object]) -> str:
        query = arguments["query"]
        limit = arguments.get("limit", 6)
        if not isinstance(query, str) or not isinstance(limit, int):
            raise ToolExecutionError(
                "tool_invalid_arguments",
                "knowledge search arguments are invalid",
            )
        result = await self._knowledge_store.search_with_mode(query, limit=limit)
        return json.dumps(
            {
                "ok": True,
                "query": query,
                "mode": result.mode,
                "degraded_reason": result.degraded_reason,
                "results": [hit.as_dict() for hit in result.results],
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def _mcp_executor(self, exposed_name: str) -> ToolExecutor:
        async def execute(arguments: dict[str, object]) -> str:
            return await self._mcp_service.invoke(exposed_name, dict(arguments))

        return execute

    @staticmethod
    def _knowledge_definition() -> ToolDefinition:
        return ToolDefinition(
            name="knowledge_search",
            description=(
                "Search the local knowledge base and return cited excerpts with document "
                "and chunk identifiers."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 500,
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 6,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            risk="low",
            timeout_seconds=5,
        )

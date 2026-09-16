from sqlalchemy.orm import Session

from app.applications.repository import (
    ApplicationRepository,
    ApplicationToolRepository,
    DependencyRepository,
    DependencyToolRepository,
)


class ApplicationContextService:
    @staticmethod
    def load(db: Session, application_id: int) -> dict:
        application = ApplicationRepository.get(db, application_id)
        if application is None:
            raise ValueError("Application not found")
        if not application.enabled:
            raise ValueError("Application is disabled")

        tools = [
            tool
            for tool in ApplicationToolRepository.list_for_application(db, application_id)
            if tool.enabled
        ]

        dependencies = []
        for dependency in DependencyRepository.list_for_application(db, application_id):
            if not dependency.enabled:
                continue
            dependency_tools = [
                item
                for item in DependencyToolRepository.list_for_dependency(db, dependency.id)
                if item.enabled
            ]
            dependencies.append(
                {
                    "id": dependency.id,
                    "name": dependency.name,
                    "type": dependency.dependency_type,
                    "description": dependency.description,
                    "tools": [
                        {
                            "id": item.id,
                            "tool_type": item.tool_type,
                            "provider_type": item.provider_type,
                            "connection_id": item.connection_id,
                            "config": item.config,
                        }
                        for item in dependency_tools
                    ],
                }
            )

        return {
            "application": {
                "id": application.id,
                "name": application.name,
                "slug": application.slug,
                "description": application.description,
                "investigation_strategy": application.investigation_strategy,
                "llm_connection_id": application.llm_connection_id,
                "llm_config": application.llm_config or {},
            },
            "tools": [
                {
                    "id": tool.id,
                    "tool_type": tool.tool_type,
                    "provider_type": tool.provider_type,
                    "connection_id": tool.connection_id,
                    "config": tool.config,
                    "priority": tool.priority,
                }
                for tool in tools
            ],
            "dependencies": dependencies,
        }

    @staticmethod
    def find_tool(context: dict, tool_type: str, provider_type: str | None = None) -> dict | None:
        for tool in context["tools"]:
            if tool["tool_type"] != tool_type:
                continue
            if provider_type is not None and tool["provider_type"] != provider_type:
                continue
            return tool
        return None

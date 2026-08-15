class UnityKnowledgeNode:
    """Retrieve optional Unity documentation evidence without invoking an LLM."""

    def __init__(self, tool, network_enabled=False):
        self.tool = tool
        self.network_enabled = bool(network_enabled)

    def run(self, state):
        state = state or {}
        contract = state.get("requirement_contract", {}) or {}
        query = contract.get("goal") if isinstance(contract, dict) else ""
        query = query or state.get("query", "")

        context = state.get("project_context", {}) or {}
        project = context.get("project", {}) if isinstance(context, dict) else {}
        unity_version = (
            project.get("unity_version", "") if isinstance(project, dict) else ""
        )
        packages = context.get("packages", []) if isinstance(context, dict) else []
        package_versions = {}
        if isinstance(packages, list):
            package_versions = {
                str(item.get("name", "")).strip(): str(item.get("version", "")).strip()
                for item in packages
                if isinstance(item, dict) and str(item.get("name", "")).strip()
            }

        result = self.tool.retrieve(
            query,
            unity_version,
            package_versions,
            allow_network=self.network_enabled,
        )
        status = result.get("status", "failed")
        return {
            "current_agent": "unity_knowledge",
            "unity_knowledge": result,
            "unity_knowledge_status": status,
            "unity_knowledge_error": result.get("error_code", ""),
            "agent_history": list(state.get("agent_history", []) or [])
            + [f"Unity Knowledge:{status}"],
        }

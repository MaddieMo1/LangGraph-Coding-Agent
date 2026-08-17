class ProjectUnderstandingNode:
    """Scan the Unity project and persist the context before planning."""

    def __init__(self, scanner, store, dependency_builder=None, dependency_store=None):
        self.scanner = scanner
        self.store = store
        self.dependency_builder = dependency_builder
        self.dependency_store = dependency_store

    def run(self, state):
        history = state.get("agent_history", [])

        try:
            context = self.scanner.scan()
            context_path = self.store.save(context)
            dependency_graph = {}
            dependency_graph_path = ""
            if self.dependency_builder and self.dependency_store:
                dependency_graph = self.dependency_builder.build(context)
                dependency_graph_path = self.dependency_store.save(dependency_graph)
        except (OSError, ValueError) as error:
            message = str(error)
            print(f"[Project Understanding]扫描失败:{message}")
            return {
                "current_agent": "project_understanding",
                "project_context_status": "failed",
                "project_context_error": message,
                "dependency_graph_status": "failed",
                "dependency_graph_error": message,
                "agent_history": history + [f"Project Understanding失败:{message}"],
            }

        print(f"[Project Understanding]扫描完成:{context_path}")
        return {
            "current_agent": "project_understanding",
            "project_context": context,
            "project_context_path": context_path,
            "project_context_status": "success",
            "project_context_error": "",
            "dependency_graph": dependency_graph,
            "dependency_graph_path": dependency_graph_path,
            "dependency_graph_status": (
                "success" if self.dependency_builder and self.dependency_store else "skipped"
            ),
            "dependency_graph_error": "",
            "agent_history": history + ["Project Understanding完成"],
        }

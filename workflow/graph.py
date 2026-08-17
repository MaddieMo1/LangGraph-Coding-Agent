# =========================
# Agent Workflow
# LangGraph工作流
# =========================

import os

from langgraph.graph import StateGraph, END

from memory.state import AgentState

from agents.coordinator import CoordinatorAgent
from agents.architecture import ArchitectureAgent
from agents.architecture_validator import ArchitectureValidator
from agents.file_planner import FilePlannerAgent
from agents.git import GitAgent
from agents.coder import CoderAgent
from agents.test_generator import TestGeneratorAgent
from agents.code_checker import CodeCheckerAgent
from agents.reviewer import ReviewerAgent
from agents.repair import RepairAgent
from agents.unity_compiler import compile_generated_sources, unity_compile_agent
from agents.unity_test import unity_test_agent
from workflow.router import router
from workflow.review_router import review_router
from workflow.task import finish_task
from workflow.project_understanding import ProjectUnderstandingNode
from workflow.unity_knowledge import UnityKnowledgeNode

from llm.invocation import RoleModel
from llm.model_router import ModelRouteError, ModelRouter
from llm.provider import build_default_providers
from memory.approval import ApprovalStore
from memory.approval_audit import ApprovalAuditError, ApprovalAuditStore, project_fingerprint
from memory.patch_history import PatchHistory
from memory.project_context import ProjectContextStore
from memory.dependency_graph import DependencyGraphStore
from memory.long_term import LongTermMemoryStore
from memory.unity_knowledge import UnityKnowledgeStore
from tools.approval_tool import ApprovalTool
from tools.approval_policy import ApprovalPolicy
from tools.change_proposal_tool import ChangeProposalTool
from tools.diff_tool import DiffTool
from tools.dependency_graph import DependencyGraphBuilder
from tools.file_manager import FileManager
from tools.git_tool import GitTool
from tools.project_scanner import UnityProjectScanner
from tools.repair_tool import RepairTool
from tools.unity_knowledge_tool import UnityKnowledgeTool
from tools.unity_docs_provider import UnityDocumentationProvider
from tools.test_generation_tool import TestGenerationTool
from workflow.human_approval import ChangeProposalNode, HumanApprovalNode
from workflow.long_term_memory import LongTermMemoryNode


class AgentWorkflow:
    """
    Agent Workflow核心工作流

    负责:
    1. Agent节点管理
    2. LangGraph流程编排
    3. 代码生成审核修复循环
    """

    def __init__(self):

        self.model_router = ModelRouter(build_default_providers())

        self.coordinator = CoordinatorAgent()

        self.architecture = ArchitectureAgent(
            RoleModel(self.model_router, "architecture")
        )

        self.architecture_validator = ArchitectureValidator(
            None
        )

        self.file_planner = FilePlannerAgent(
            RoleModel(self.model_router, "file_planner")
        )

        self.code_checker = CodeCheckerAgent()

        self.reviewer = ReviewerAgent(
            RoleModel(self.model_router, "reviewer")
        )

        self.file_manager = FileManager()

        day06_path = os.path.dirname(
            os.path.dirname(
                os.path.abspath(__file__)
            )
        )

        self.test_generator = TestGeneratorAgent(
            RoleModel(self.model_router, "test_generator"),
            TestGenerationTool(
                os.getenv(
                    "GENERATED_TEST_SOURCE_PATH",
                    os.path.join(day06_path, "generated_tests"),
                )
            )
        )

        unity_project_path = os.getenv(
            "UNITY_TEST_PROJECT_PATH",
            r"D:\Unity\Unity_Project\CodingAgentTest"
        )

        self.long_term_memory = LongTermMemoryNode(
            LongTermMemoryStore(
                os.getenv(
                    "LONG_TERM_MEMORY_PATH",
                    os.path.join(day06_path, "memory", "long_term_memory.json")
                )
            ),
            unity_project_path,
        )

        self.project_understanding = ProjectUnderstandingNode(
            UnityProjectScanner(unity_project_path),
            ProjectContextStore(
                os.getenv(
                    "PROJECT_CONTEXT_PATH",
                    os.path.join(day06_path, "memory", "project_context.json"),
                )
            ),
            DependencyGraphBuilder(),
            DependencyGraphStore(
                os.getenv(
                    "DEPENDENCY_GRAPH_PATH",
                    os.path.join(day06_path, "memory", "dependency_graph.json"),
                )
            ),
        )

        self.unity_knowledge = UnityKnowledgeNode(
            UnityKnowledgeTool(
                UnityKnowledgeStore(
                    os.getenv(
                        "UNITY_KNOWLEDGE_CACHE_PATH",
                        os.path.join(day06_path, "memory", "unity_knowledge_cache.json"),
                    )
                ),
                provider=UnityDocumentationProvider(),
            ),
            network_enabled=(
                os.getenv("UNITY_KNOWLEDGE_NETWORK_ENABLED", "").strip().lower()
                in {"1", "true", "yes"}
            ),
        )

        generated_path = os.path.realpath(
            os.path.abspath(
                os.getenv(
                    "GENERATED_SOURCE_PATH",
                    os.path.join(day06_path, "generated")
                )
            )
        )

        self.approval_policy = ApprovalPolicy.from_environment()
        self.approval_audit = ApprovalAuditStore(
            os.getenv(
                "APPROVAL_AUDIT_PATH",
                os.path.join(day06_path, "memory", "approval_audit.jsonl"),
            ),
            project_fingerprint(generated_path),
        )

        self.git_agent = GitAgent(
            GitTool(generated_path)
        )

        self.diff_tool = DiffTool(
            self.file_manager,
            generated_path
        )

        self.patch_history = PatchHistory(
            os.getenv(
                "PATCH_HISTORY_PATH",
                os.path.join(day06_path, "memory", "patch_history.json"),
            ),
            self.diff_tool
        )

        self.approval_store = ApprovalStore(
            os.getenv(
                "APPROVAL_HISTORY_PATH",
                os.path.join(day06_path, "memory", "approval_history.json")
            )
        )

        self.change_proposal_tool = ChangeProposalTool(
            self.file_manager,
            generated_path,
            self.diff_tool
        )

        self.approval_tool = ApprovalTool(
            self.approval_store,
            self.diff_tool,
            self.patch_history,
            audit_store=self.approval_audit,
        )

        self.change_proposal = ChangeProposalNode(
            self.change_proposal_tool,
            self.approval_store,
            approval_policy=self.approval_policy,
            audit_store=self.approval_audit,
        )

        self.human_approval = HumanApprovalNode(
            self.approval_tool,
            approval_policy=self.approval_policy,
            audit_store=self.approval_audit,
        )

        self.coder = CoderAgent(
            RoleModel(self.model_router, "coder"),
            generated_path
        )

        self.repair_tool = RepairTool(
            self.file_manager,
            generated_path,
            self.diff_tool,
            self.patch_history
        )

        self.repair = RepairAgent(
            RoleModel(self.model_router, "repair"),
            self.repair_tool
        )

        self.workflow = StateGraph(
            AgentState
        )

        self.build_graph()


    def coordinator_node(self,state):
        """
        Coordinator节点

        Returns:
            更新后的状态
        """

        return self.coordinator.run(
            state
        )


    def git_prepare_node(self, state):
        return self.git_agent.prepare(state)


    def git_commit_node(self, state):
        validation_passed = self._validation_passed(state)
        try:
            self._record_system_audit(
                state,
                "validation_completed",
                "quality_gates",
                "passed" if validation_passed else "failed",
                "" if validation_passed else "VALIDATION_FAILED",
                idempotency_key=f"validation:{state.get('thread_id', '')}",
            )
        except ApprovalAuditError as error:
            return self._git_audit_error(error)

        result = self.git_agent.commit(state)
        if result.get("git_status") != "committed":
            return result

        git_result = result.get("git_result", {})
        note = (
            f"branch={git_result.get('branch', '')};"
            f"base={git_result.get('base_commit', '')};"
            f"commit={git_result.get('commit_hash', '')}"
        )
        try:
            self._record_system_audit(
                state,
                "git_committed",
                "commit",
                "committed",
                "",
                note=note,
                idempotency_key=(
                    f"git:{state.get('thread_id', '')}:"
                    f"{git_result.get('commit_hash', '')}"
                ),
            )
        except ApprovalAuditError as error:
            return self._git_audit_error(error)
        return result

    @staticmethod
    def _validation_passed(state):
        review = state.get("review", {})
        return (
            state.get("code_check_result", {}).get("success", False)
            and state.get("compile_result", {}).get("success", False)
            and state.get("test_result", {}).get("success", False)
            and isinstance(review, dict)
            and review.get("pass", False)
            and review.get("score", 0) >= 90
            and not review.get("remaining_issues", [])
        )

    def _record_system_audit(
        self,
        state,
        event_type,
        action,
        result,
        error_code,
        note="",
        idempotency_key="",
    ):
        actor = ApprovalPolicy.system_actor()
        thread_id = str(state.get("thread_id", "") or "")
        bundle_id = self._latest_bundle_id(state) or f"task-{thread_id}"
        self.approval_audit.append(
            {
                "event_type": event_type,
                "thread_id": thread_id,
                "bundle_id": bundle_id,
                "source": "system",
                "actor_id": actor.actor_id,
                "role": actor.role,
                "files": self._approved_audit_files(state),
                "action": action,
                "result": result,
                "note": note,
                "error_code": error_code,
            },
            idempotency_key=idempotency_key,
        )

    def _approved_audit_files(self, state):
        approved = {
            item.get("file")
            for item in state.get("approved_changes", [])
            if isinstance(item, dict)
        }
        files = {}
        for history in state.get("approval_history", []):
            if not isinstance(history, dict):
                continue
            bundle = self.approval_store.get(history.get("bundle_id", "")) or {}
            for patch in bundle.get("patches", []):
                if patch.get("file") in approved:
                    files[patch["file"]] = {
                        "file": patch["file"],
                        "operation": patch["operation"],
                        "before_hash": patch["before_hash"],
                        "after_hash": patch["after_hash"],
                    }
        return [files[file_name] for file_name in sorted(files)]

    @staticmethod
    def _latest_bundle_id(state):
        for item in reversed(state.get("approval_history", [])):
            if isinstance(item, dict) and item.get("bundle_id"):
                return item["bundle_id"]
        return state.get("approval_request", {}).get("bundle_id", "")

    @staticmethod
    def _git_audit_error(error):
        return {
            "current_agent": "git_commit",
            "git_status": "error",
            "git_result": {
                "success": False,
                "error_code": getattr(error, "code", "AUDIT_FAILED"),
                "error": str(error),
            },
        }


    def git_prepare_router(self, state):
        return "baseline_compiler" if state.get("git_status") == "prepared" else "finish_task"


    def baseline_compiler_node(self, state):
        result = compile_generated_sources()
        return {
            "baseline_compile_result": result,
            "baseline_compile_status": "passed" if result.get("success") else "failed",
            "current_agent": "baseline_compiler",
            "agent_history": state.get("agent_history", [])
            + ["Baseline Compiler完成"],
        }


    def baseline_compiler_router(self, state):
        return (
            "coordinator"
            if state.get("baseline_compile_result", {}).get("success", False)
            else "finish_task"
        )


    def architecture_node(self,state):
        """
        Architecture Agent节点
        """

        return self._run_model_node(self.architecture.run, state)


    @staticmethod
    def _run_model_node(run, state):
        try:
            return run(state)
        except ModelRouteError as error:
            return {
                "current_agent": "finish_task",
                "model_error": dict(error.result),
                "model_route": dict(error.result),
                "model_routing_history": (
                    list(state.get("model_routing_history", []) or [])
                    + [dict(error.result)]
                )[-100:],
                "agent_history": list(state.get("agent_history", []) or [])
                + ["模型路由失败，任务安全结束"],
            }


    @staticmethod
    def model_node_router(state, success_node):
        return "finish_task" if state.get("model_error") else success_node


    def project_understanding_node(self,state):
        result = self.project_understanding.run(state)
        merged_state = {**state, **result}
        return {**result, **self.long_term_memory.update_project(merged_state)}


    def unity_compiler_node(self, state):
        result = unity_compile_agent(state)
        return {**result, **self.long_term_memory.observe_compile(result)}


    def unity_knowledge_node(self, state):
        return self.unity_knowledge.run(state)


    def unity_test_node(self, state):
        result = unity_test_agent(state)
        merged_state = {**state, **result}
        return {**result, **self.long_term_memory.observe_test(merged_state)}


    def project_understanding_router(self,state):
        if (
            state.get("project_context_status") != "success"
            or state.get("dependency_graph_status") != "success"
        ):
            return "finish_task"
        return "unity_knowledge"


    def architecture_validator_node(self,state):
        """
        架构验证节点
        """

        result = self.architecture_validator.validate(
            state.get(
                "architecture",
                ""
            )
        )

        print(
            f"[Architecture Validator]结果:{result.get('pass')}"
        )

        return {
            "architecture_validation":result
        }


    def file_planner_node(self,state):
        """
        文件规划节点
        """

        return self._run_model_node(self.file_planner.run, state)


    def coder_node(self,state):
        """
        代码生成节点
        """

        return self._run_model_node(self.coder.run, state)


    def code_checker_node(self,state):
        """
        代码检查节点
        """

        return self.code_checker.run(
            state
        )


    def test_generator_node(self,state):
        return self._run_model_node(self.test_generator.run, state)


    def test_generator_router(self,state):
        if not state.get("test_generation_result", {}).get("success", False):
            return "finish_task"
        return router(state)


    def reviewer_node(self,state):
        """
        代码审核节点
        """

        return self._run_model_node(self.reviewer.run, state)


    def repair_node(self,state):
        """
        修复节点
        """

        return self._run_model_node(self.repair.run, state)


    def change_proposal_node(self,state):
        return self.change_proposal.run(state)


    def human_approval_node(self,state):
        return self.human_approval.run(state)


    def change_proposal_router(self,state):
        status = state.get("approval_status", "")
        source = state.get("proposal_source", "")

        if status == "pending":
            return "human_approval"

        if status == "no_changes":
            return "test_generator" if source == "coder" else "code_checker"

        return "finish_task"


    def human_approval_router(self,state):
        status = state.get("approval_status", "")
        source = state.get("proposal_source", "")

        if status in {"approved", "partially_approved"}:
            return "test_generator" if source == "coder" else "code_checker"

        return "finish_task"


    def unity_compiler_router(self,state):
        """
        Unity Compiler结果路由
        """

        compile_result = state.get(
            "compile_result",
            {}
        )


        if compile_result.get(
            "system_error",
            False
        ):

            print(
                "[Unity Compiler Router]系统错误，终止修复循环"
            )

            return "finish_task"


        if compile_result.get("success", False):
            return "unity_test"

        return "reviewer"


    def unity_test_router(self,state):
        test_result = state.get("test_result", {})
        if test_result.get("error_code") == "TEST_ASSEMBLY_COMPILE_ERROR":
            return "finish_task"
        if test_result.get("system_error", False):
            return "finish_task"
        return "reviewer"


    def finish_node(self,state):
        """
        工作流结束
        """

        return finish_task(
            state
        )


    def architecture_router(self,state):
        """
        架构验证路由
        """

        result = state.get(
            "architecture_validation",
            {}
        )

        if result.get(
            "pass",
            False
        ):
            print(
                "[Architecture Router]架构通过"
            )

            return "file_planner"


        print(
            "[Architecture Router]架构失败"
        )

        return "architecture"


    def build_graph(self):

        self.workflow.add_node(
            "git_prepare",
            self.git_prepare_node
        )

        self.workflow.add_node(
            "baseline_compiler",
            self.baseline_compiler_node
        )

        self.workflow.add_node(
            "coordinator",
            self.coordinator_node
        )

        self.workflow.add_node(
            "project_understanding",
            self.project_understanding_node
        )

        self.workflow.add_node(
            "unity_knowledge",
            self.unity_knowledge_node
        )

        self.workflow.add_node(
            "architecture",
            self.architecture_node
        )

        self.workflow.add_node(
            "architecture_validator",
            self.architecture_validator_node
        )

        self.workflow.add_node(
            "file_planner",
            self.file_planner_node
        )

        self.workflow.add_node(
            "coder",
            self.coder_node
        )

        self.workflow.add_node(
            "change_proposal",
            self.change_proposal_node
        )

        self.workflow.add_node(
            "human_approval",
            self.human_approval_node
        )

        self.workflow.add_node(
            "code_checker",
            self.code_checker_node
        )

        self.workflow.add_node(
            "test_generator",
            self.test_generator_node
        )

        self.workflow.add_node(
            "reviewer",
            self.reviewer_node
        )

        self.workflow.add_node(
            "repair",
            self.repair_node
        )

        self.workflow.add_node(
            "finish_task",
            self.finish_node
        )

        self.workflow.add_node(
            "debug_start",
            lambda state: state
        )

        self.workflow.add_node(
            "unity_compiler",
            self.unity_compiler_node
        )

        self.workflow.add_node(
            "unity_test",
            self.unity_test_node
        )

        self.workflow.add_node(
            "git_commit",
            self.git_commit_node
        )


        self.workflow.set_entry_point(
            "git_prepare"
        )


        # Git preparation
        self.workflow.add_conditional_edges(
            "git_prepare",
            self.git_prepare_router,
            {
                "baseline_compiler":"baseline_compiler",
                "finish_task":"finish_task"
            }
        )

        self.workflow.add_conditional_edges(
            "baseline_compiler",
            self.baseline_compiler_router,
            {
                "coordinator":"coordinator",
                "finish_task":"finish_task"
            }
        )


        # Coordinator
        self.workflow.add_conditional_edges(
            "coordinator",
            router,
            {
                "project_understanding":"project_understanding",
                "architecture":"architecture",
                "file_planner":"file_planner",
                "coder":"coder",
                "test_generator":"test_generator",
                "code_checker":"code_checker",
                "reviewer":"reviewer",
                "finish_task":"finish_task"
            }
        )


        # Project Understanding
        self.workflow.add_conditional_edges(
            "project_understanding",
            self.project_understanding_router,
            {
                "unity_knowledge":"unity_knowledge",
                "finish_task":"finish_task"
            }
        )

        self.workflow.add_edge(
            "unity_knowledge",
            "architecture"
        )


        # Architecture
        self.workflow.add_conditional_edges(
            "architecture",
            lambda state: self.model_node_router(state, "architecture_validator"),
            {
                "architecture_validator":"architecture_validator",
                "finish_task":"finish_task"
            }
        )


        # Architecture Validator
        self.workflow.add_conditional_edges(
            "architecture_validator",
            self.architecture_router,
            {
                "file_planner":"file_planner",
                "architecture":"architecture"
            }
        )


        # File Planner
        self.workflow.add_conditional_edges(
            "file_planner",
            lambda state: "finish_task" if state.get("model_error") else router(state),
            {
                "file_planner":"file_planner",
                "coder":"coder",
                "finish_task":"finish_task"
            }
        )


        # Coder
        self.workflow.add_conditional_edges(
            "coder",
            lambda state: self.model_node_router(state, "change_proposal"),
            {
                "change_proposal":"change_proposal",
                "finish_task":"finish_task"
            }
        )


        # Change Proposal
        self.workflow.add_conditional_edges(
            "change_proposal",
            self.change_proposal_router,
            {
                "human_approval":"human_approval",
                "test_generator":"test_generator",
                "code_checker":"code_checker",
                "finish_task":"finish_task"
            }
        )


        # Human Approval
        self.workflow.add_conditional_edges(
            "human_approval",
            self.human_approval_router,
            {
                "test_generator":"test_generator",
                "code_checker":"code_checker",
                "finish_task":"finish_task"
            }
        )


        # Test Generator
        self.workflow.add_conditional_edges(
            "test_generator",
            self.test_generator_router,
            {
                "code_checker":"code_checker",
                "finish_task":"finish_task"
            }
        )


        # Code Checker
        self.workflow.add_edge(
            "code_checker",
            "unity_compiler"
        )


        self.workflow.add_conditional_edges(
            "unity_compiler",
            self.unity_compiler_router,
            {
                "unity_test":"unity_test",
                "reviewer":"reviewer",
                "finish_task":"finish_task"
            }
        )


        # Unity Test
        self.workflow.add_conditional_edges(
            "unity_test",
            self.unity_test_router,
            {
                "reviewer":"reviewer",
                "finish_task":"finish_task"
            }
        )


        # Reviewer
        self.workflow.add_conditional_edges(
            "reviewer",
            review_router,
            {
                "reviewer":"reviewer",
                "repair":"repair",
                "architecture":"architecture",
                "git_commit":"git_commit",
                "finish_task":"finish_task"
            }
        )


        # Repair
        self.workflow.add_conditional_edges(
            "repair",
            lambda state: self.model_node_router(state, "change_proposal"),
            {
                "change_proposal":"change_proposal",
                "finish_task":"finish_task"
            }
        )


        self.workflow.add_edge(
            "finish_task",
            END
        )


        self.workflow.add_edge(
            "git_commit",
            "finish_task"
        )


    def compile_debug(self, checkpointer=None):

        self.workflow.set_entry_point(
            "debug_start"
        )

        return self.workflow.compile(checkpointer=checkpointer)

    def compile(self, checkpointer=None):
        """
        编译Workflow

        Returns:
            LangGraph应用
        """

        return self.workflow.compile(checkpointer=checkpointer)

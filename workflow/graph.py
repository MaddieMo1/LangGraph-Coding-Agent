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
from agents.coder import CoderAgent
from agents.test_generator import TestGeneratorAgent
from agents.code_checker import CodeCheckerAgent
from agents.reviewer import ReviewerAgent
from agents.repair import RepairAgent
from agents.unity_compiler import unity_compile_agent
from agents.unity_test import unity_test_agent
from workflow.router import router
from workflow.review_router import review_router
from workflow.task import finish_task
from workflow.project_understanding import ProjectUnderstandingNode

from llm.deepseek import DeepSeekLLM
from memory.patch_history import PatchHistory
from memory.project_context import ProjectContextStore
from memory.dependency_graph import DependencyGraphStore
from tools.diff_tool import DiffTool
from tools.dependency_graph import DependencyGraphBuilder
from tools.file_manager import FileManager
from tools.project_scanner import UnityProjectScanner
from tools.repair_tool import RepairTool
from tools.test_generation_tool import TestGenerationTool


class AgentWorkflow:
    """
    Agent Workflow核心工作流

    负责:
    1. Agent节点管理
    2. LangGraph流程编排
    3. 代码生成审核修复循环
    """

    def __init__(self):

        self.llm = DeepSeekLLM()

        self.coordinator = CoordinatorAgent()

        self.architecture = ArchitectureAgent(
            self.llm
        )

        self.architecture_validator = ArchitectureValidator(
            self.llm
        )

        self.file_planner = FilePlannerAgent(
            self.llm
        )

        self.coder = CoderAgent()

        self.code_checker = CodeCheckerAgent()

        self.reviewer = ReviewerAgent(
            self.llm
        )

        self.file_manager = FileManager()

        day06_path = os.path.dirname(
            os.path.dirname(
                os.path.abspath(__file__)
            )
        )

        self.test_generator = TestGeneratorAgent(
            self.llm,
            TestGenerationTool(
                os.path.join(day06_path, "generated_tests")
            )
        )

        unity_project_path = os.getenv(
            "UNITY_TEST_PROJECT_PATH",
            r"D:\Unity\Unity_Project\CodingAgentTest"
        )

        self.project_understanding = ProjectUnderstandingNode(
            UnityProjectScanner(unity_project_path),
            ProjectContextStore(
                os.path.join(
                    day06_path,
                    "memory",
                    "project_context.json"
                )
            ),
            DependencyGraphBuilder(),
            DependencyGraphStore(
                os.path.join(
                    day06_path,
                    "memory",
                    "dependency_graph.json"
                )
            ),
        )

        generated_path = os.path.join(
            day06_path,
            "generated"
        )

        self.diff_tool = DiffTool(
            self.file_manager,
            generated_path
        )

        self.patch_history = PatchHistory(
            os.path.join(
                day06_path,
                "memory",
                "patch_history.json"
            ),
            self.diff_tool
        )

        self.repair_tool = RepairTool(
            self.file_manager,
            generated_path,
            self.diff_tool,
            self.patch_history
        )

        self.repair = RepairAgent(
            self.llm,
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


    def architecture_node(self,state):
        """
        Architecture Agent节点
        """

        return self.architecture.run(
            state
        )


    def project_understanding_node(self,state):
        return self.project_understanding.run(state)


    def project_understanding_router(self,state):
        if (
            state.get("project_context_status") != "success"
            or state.get("dependency_graph_status") != "success"
        ):
            return "finish_task"
        return router(state)


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

        return self.file_planner.run(
            state
        )


    def coder_node(self,state):
        """
        代码生成节点
        """

        return self.coder.run(
            state
        )


    def code_checker_node(self,state):
        """
        代码检查节点
        """

        return self.code_checker.run(
            state
        )


    def test_generator_node(self,state):
        return self.test_generator.run(state)


    def test_generator_router(self,state):
        if not state.get("test_generation_result", {}).get("success", False):
            return "finish_task"
        return router(state)


    def reviewer_node(self,state):
        """
        代码审核节点
        """

        return self.reviewer.run(
            state
        )


    def repair_node(self,state):
        """
        修复节点
        """

        return self.repair.run(
            state
        )


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
            "coordinator",
            self.coordinator_node
        )

        self.workflow.add_node(
            "project_understanding",
            self.project_understanding_node
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
            unity_compile_agent
        )

        self.workflow.add_node(
            "unity_test",
            unity_test_agent
        )


        self.workflow.set_entry_point(
            "coordinator"
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
                "architecture":"architecture",
                "finish_task":"finish_task"
            }
        )


        # Architecture
        self.workflow.add_edge(
            "architecture",
            "architecture_validator"
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
            router,
            {
                "file_planner":"file_planner",
                "coder":"coder",
                "finish_task":"finish_task"
            }
        )


        # Coder
        self.workflow.add_conditional_edges(
            "coder",
            router,
            {
                "coder":"coder",
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
                "finish_task":"finish_task"
            }
        )


        # Repair
        self.workflow.add_edge(
            "repair",
            "code_checker"
        )


        self.workflow.add_edge(
            "finish_task",
            END
        )


    def compile_debug(self):

        self.workflow.set_entry_point(
            "debug_start"
        )

        return self.workflow.compile()

    def compile(self):
        """
        编译Workflow

        Returns:
            LangGraph应用
        """

        return self.workflow.compile()

import os
import tempfile
import unittest
from typing import Any, Dict, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from memory.approval import ApprovalStore
from memory.patch_history import PatchHistory
from tools.approval_tool import ApprovalTool
from tools.change_proposal_tool import ChangeProposalTool
from tools.diff_tool import DiffTool
from tools.file_manager import FileManager
from workflow.graph import AgentWorkflow
from workflow.human_approval import ChangeProposalNode, HumanApprovalNode


class ApprovalState(TypedDict, total=False):
    proposal_source: str
    proposed_changes: list
    approval_request: Dict[str, Any]
    approval_result: Dict[str, Any]
    approval_history: list
    approval_status: str
    code: list
    current_agent: str


class Day11WorkflowTest(unittest.TestCase):
    def test_proposal_router_sends_pending_request_to_human(self):
        self.assertEqual(
            "human_approval",
            AgentWorkflow.change_proposal_router(
                None,
                {"approval_status": "pending", "proposal_source": "coder"},
            ),
        )
        self.assertEqual(
            "test_generator",
            AgentWorkflow.change_proposal_router(
                None,
                {"approval_status": "no_changes", "proposal_source": "coder"},
            ),
        )
        self.assertEqual(
            "code_checker",
            AgentWorkflow.change_proposal_router(
                None,
                {"approval_status": "no_changes", "proposal_source": "repair"},
            ),
        )

    def test_approval_router_uses_source_and_stops_rejections(self):
        self.assertEqual(
            "test_generator",
            AgentWorkflow.human_approval_router(
                None,
                {"approval_status": "approved", "proposal_source": "coder"},
            ),
        )
        self.assertEqual(
            "code_checker",
            AgentWorkflow.human_approval_router(
                None,
                {"approval_status": "partially_approved", "proposal_source": "repair"},
            ),
        )
        self.assertEqual(
            "finish_task",
            AgentWorkflow.human_approval_router(
                None,
                {"approval_status": "rejected", "proposal_source": "coder"},
            ),
        )

    def test_real_interrupt_and_resume_applies_coder_bundle(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            generated_root = os.path.join(temporary_directory, "generated")
            os.makedirs(generated_root)
            file_manager = FileManager()
            diff_tool = DiffTool(file_manager, generated_root)
            store = ApprovalStore(os.path.join(temporary_directory, "approvals.json"))
            proposal_node = ChangeProposalNode(
                ChangeProposalTool(file_manager, generated_root, diff_tool),
                store,
            )
            approval_node = HumanApprovalNode(
                ApprovalTool(
                    store,
                    diff_tool,
                    PatchHistory(os.path.join(temporary_directory, "patches.json"), diff_tool),
                )
            )
            builder = StateGraph(ApprovalState)
            builder.add_node("proposal", proposal_node.run)
            builder.add_node("approval", approval_node.run)
            builder.add_edge(START, "proposal")
            builder.add_edge("proposal", "approval")
            builder.add_edge("approval", END)
            graph = builder.compile(checkpointer=InMemorySaver())
            config = {"configurable": {"thread_id": "coder-approval"}}

            interrupted = graph.invoke(
                {
                    "proposal_source": "coder",
                    "proposed_changes": [{"file": "A.cs", "content": "class A {}\n"}],
                    "approval_history": [],
                    "code": [{"file": "A.cs", "content": "class A {}\n"}],
                },
                config=config,
            )
            payload = interrupted["__interrupt__"][0].value
            resumed = graph.invoke(
                Command(
                    resume={
                        "bundle_id": payload["bundle_id"],
                        "action": "approve",
                        "mode": "batch",
                    }
                ),
                config=config,
            )

            self.assertEqual("approved", resumed["approval_status"])
            self.assertTrue(os.path.isfile(os.path.join(generated_root, "A.cs")))


if __name__ == "__main__":
    unittest.main()

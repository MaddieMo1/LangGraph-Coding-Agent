from html import escape

import gradio as gr


APPROVAL_CSS = """
.gradio-container {
    max-width: 1240px !important;
    margin: 0 auto;
    padding: 32px 24px 56px !important;
}
#hero { padding: 20px 4px 28px; }
#hero h1 {
    max-width: 760px;
    margin: 8px 0 10px;
    font-size: clamp(30px, 4vw, 48px);
    line-height: 1.08;
    letter-spacing: -0.035em;
}
#hero p { max-width: 720px; color: var(--body-text-color-subdued); font-size: 16px; }
#hero .eyebrow {
    color: var(--primary-600);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: .14em;
}
.surface {
    border: 1px solid var(--border-color-primary) !important;
    border-radius: 16px !important;
    background: var(--background-fill-primary) !important;
    box-shadow: 0 10px 30px rgba(15, 23, 42, .06) !important;
}
#task-card { padding: 20px 20px 8px; margin-bottom: 16px; }
#task-card h2, #review-heading h2 { margin: 0 0 4px; font-size: 18px; }
#task-card p, #review-heading p { color: var(--body-text-color-subdued); }
#recovery { margin: 4px 0 20px; }
#status-card {
    padding: 16px 18px;
    margin-bottom: 12px;
    border: 1px solid var(--border-color-primary);
    border-radius: 14px;
    background: var(--background-fill-secondary);
}
#status-card p { margin: 0; }
.status-line { display: flex; gap: 12px; align-items: flex-start; }
.status-badge {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    min-height: 26px;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 700;
}
.status-copy { padding-top: 2px; color: var(--body-text-color); }
.status-idle .status-badge { color: #475569; background: #e2e8f0; }
.status-pending .status-badge { color: #92400e; background: #fef3c7; }
.status-approved .status-badge,
.status-partially_approved .status-badge,
.status-completed .status-badge { color: #166534; background: #dcfce7; }
.status-rejected .status-badge,
.status-conflicted .status-badge { color: #991b1b; background: #fee2e2; }
#review-meta {
    min-height: 46px;
    padding: 0 4px 10px;
    color: var(--body-text-color-subdued);
}
#review-meta strong { color: var(--body-text-color); }
#review-workspace { gap: 16px; align-items: stretch; }
#file-panel, #diff-panel { padding: 16px; }
#file-panel { min-width: 280px; }
#diff-panel { min-width: 0; }
#diff-panel .code_wrap { border-radius: 12px; }
#decision-card { padding: 18px; margin-top: 16px; }
#decision-card .form { border: none; background: transparent; }
#decision-actions { gap: 10px; }
#approve-all { order: 1; }
#approve-selected { order: 2; }
#reject-all { order: 3; }
@media (max-width: 760px) {
    .gradio-container { padding: 20px 14px 40px !important; }
    #hero { padding-top: 8px; }
    #review-workspace { flex-direction: column; }
    #file-panel, #diff-panel { min-width: 100%; }
    #decision-actions { flex-direction: column; }
}
"""


STATUS_LABELS = {
    "idle": "尚未开始",
    "pending": "等待审批",
    "approved": "已批准",
    "partially_approved": "部分批准",
    "rejected": "已拒绝",
    "conflicted": "存在冲突",
    "completed": "已完成",
}

SOURCE_LABELS = {"coder": "Coder 初始提案", "repair": "Repair 修复提案"}
OPERATION_LABELS = {"create": "新增", "modify": "修改", "delete": "删除"}


def format_status_card(status, message):
    safe_status = status if status in STATUS_LABELS else "idle"
    label = STATUS_LABELS.get(status, status or STATUS_LABELS["idle"])
    return (
        f'<div class="status-line status-{safe_status}">'
        f'<span class="status-badge">{escape(label)}</span>'
        f'<span class="status-copy">{escape(message)}</span>'
        "</div>"
    )


def format_review_meta(source, patch_count):
    if not patch_count:
        return "暂无待审批变更。启动新任务，或从下方恢复已有任务。"
    source_label = SOURCE_LABELS.get(source, source or "未知来源")
    return f"提案来自 **{source_label}** · 共 **{patch_count} 个文件**等待确认"


def patch_choices(patches):
    return [
        (
            f"{patch['file']} · {OPERATION_LABELS.get(patch['operation'], patch['operation'])}",
            patch["patch_id"],
        )
        for patch in patches
    ]


def select_patch_diff(patches, patch_id):
    for patch in patches or []:
        if patch.get("patch_id") == patch_id:
            return patch.get("diff", "")
    return ""


class ApprovalController:
    """Testable callbacks for starting, recovering, and deciding workflow reviews."""

    def __init__(self, runtime):
        self.runtime = runtime

    def start(self, query):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("请输入任务需求")
        thread_id = self.runtime.new_thread_id()
        result = self.runtime.invoke(self._initial_state(query.strip()), thread_id)
        return self._view_from_result(thread_id, result)

    def reload(self, thread_id):
        snapshot = self.runtime.get_state(thread_id)
        return self._view_from_result(thread_id.strip(), snapshot.values)

    def accept_all(self, thread_id, bundle_id, note):
        return self._decide(
            thread_id,
            {
                "bundle_id": bundle_id,
                "action": "approve",
                "mode": "batch",
                "note": note or "",
            },
        )

    def reject_all(self, thread_id, bundle_id, note):
        return self._decide(
            thread_id,
            {
                "bundle_id": bundle_id,
                "action": "reject",
                "mode": "batch",
                "note": note or "",
            },
        )

    def accept_selected(self, thread_id, bundle_id, patch_ids, note):
        return self._decide(
            thread_id,
            {
                "bundle_id": bundle_id,
                "action": "approve",
                "mode": "selected",
                "accepted_patch_ids": list(patch_ids or []),
                "note": note or "",
            },
        )

    def _decide(self, thread_id, decision):
        if not decision.get("bundle_id"):
            raise ValueError("当前没有可审批的变更包")
        result = self.runtime.resume(thread_id, decision)
        return self._view_from_result(thread_id.strip(), result)

    @staticmethod
    def _initial_state(query):
        return {
            "query": query,
            "current_agent": "",
            "agent_history": [],
            "requirements": [],
            "context": [],
            "architecture": "",
            "code": [],
            "review": "",
            "tools": [],
            "tokens": 0,
            "approval_history": [],
        }

    @classmethod
    def _view_from_result(cls, thread_id, result):
        request = cls._interrupt_request(result) or result.get("approval_request", {})
        status = result.get("approval_status", request.get("status", "completed"))
        approval_result = result.get("approval_result", {})
        patches = request.get("patches", []) if status == "pending" else []
        selected = [patch["patch_id"] for patch in patches]
        message = cls._status_message(status, approval_result)
        return {
            "thread_id": thread_id,
            "bundle_id": request.get("bundle_id", approval_result.get("bundle_id", "")),
            "status": status,
            "source": request.get("source", ""),
            "patches": patches,
            "selected_patch_ids": selected,
            "diff": patches[0].get("diff", "") if patches else "",
            "message": message,
        }

    @staticmethod
    def _interrupt_request(result):
        interrupts = result.get("__interrupt__", [])
        if not interrupts:
            return {}
        first = interrupts[0]
        return first.value if hasattr(first, "value") else first.get("value", {})

    @staticmethod
    def _status_message(status, approval_result):
        error = approval_result.get("error", "")
        if error:
            return f"{status}: {error}"
        if approval_result.get("already_decided", False):
            return f"{status}: 该审批已处理，没有重复应用变更。"
        messages = {
            "pending": "工作流已暂停，等待人工审批。",
            "approved": "全部变更已批准并应用，工作流已继续。",
            "partially_approved": "所选变更已原子应用，工作流已继续。",
            "rejected": "变更已拒绝，未写入生产文件。",
            "conflicted": "源文件已变化，审批冲突且未写入任何变更。",
            "completed": "工作流已完成。",
        }
        return messages.get(status, f"工作流状态：{status}")


def build_approval_app(controller):
    with gr.Blocks(title="Coding Agent · Human Approval") as demo:
        gr.Markdown(
            '<div class="eyebrow">DAY 11 · HUMAN IN THE LOOP</div>\n'
            "# 让每一次代码写入，都经过确认\n"
            "在 AI 生成的生产代码落盘前，集中查看变更、判断风险，并明确批准或拒绝。",
            elem_id="hero",
        )
        bundle_state = gr.State("")
        patches_state = gr.State([])

        with gr.Group(elem_id="task-card", elem_classes="surface"):
            gr.Markdown(
                "## 01 · 发起任务\n"
                "描述你希望 Coding Agent 完成的工作，系统会在首次写入前自动暂停。"
            )
            with gr.Row(equal_height=True):
                query = gr.Textbox(
                    label="任务需求",
                    placeholder="例如：设计 Unity 背包系统并生成代码",
                    lines=3,
                    scale=5,
                )
                start_button = gr.Button(
                    "开始并生成提案",
                    variant="primary",
                    scale=1,
                    min_width=180,
                )

        with gr.Accordion("恢复已有任务", open=False, elem_id="recovery"):
            with gr.Row(equal_height=True):
                thread_id = gr.Textbox(
                    label="任务 ID",
                    placeholder="粘贴任务 ID，恢复中断或待审批的任务",
                    scale=5,
                )
                reload_button = gr.Button("恢复任务", scale=1, min_width=150)

        gr.Markdown(
            "## 02 · 审阅变更\n"
            "先逐个核对文件，再决定批准全部、仅批准所选，或拒绝本次提案。",
            elem_id="review-heading",
        )
        status = gr.HTML(
            format_status_card("idle", "输入任务需求后开始，系统会在需要审批时停在这里。"),
            elem_id="status-card",
        )
        review_meta = gr.Markdown(format_review_meta("", 0), elem_id="review-meta")

        with gr.Row(elem_id="review-workspace"):
            with gr.Column(scale=2, elem_id="file-panel", elem_classes="surface"):
                patch_picker = gr.Dropdown(
                    label="当前查看文件",
                    choices=[],
                    interactive=False,
                )
                with gr.Accordion("按文件选择批准范围", open=False):
                    selected_patches = gr.CheckboxGroup(
                        label="准备批准的文件",
                        choices=[],
                        info="所选文件会作为一个原子批次应用；未选文件不会写入。",
                        interactive=False,
                    )
            with gr.Column(scale=5, elem_id="diff-panel", elem_classes="surface"):
                diff = gr.Code(
                    label="统一 Diff · 只读",
                    language=None,
                    lines=22,
                    interactive=False,
                )

        with gr.Group(elem_id="decision-card", elem_classes="surface"):
            note = gr.Textbox(
                label="审批备注（可选）",
                placeholder="记录批准原因、风险说明或后续处理建议",
                lines=2,
                interactive=False,
            )
            with gr.Row(elem_id="decision-actions"):
                accept_all = gr.Button(
                    "批准全部并继续",
                    variant="primary",
                    interactive=False,
                    elem_id="approve-all",
                )
                accept_selected = gr.Button(
                    "仅应用所选文件",
                    interactive=False,
                    elem_id="approve-selected",
                )
                reject_all = gr.Button(
                    "拒绝本次提案",
                    variant="stop",
                    interactive=False,
                    elem_id="reject-all",
                )

        def render(view):
            choices = patch_choices(view["patches"])
            first = view["selected_patch_ids"][0] if view["selected_patch_ids"] else None
            pending = view["status"] == "pending"
            return (
                view["thread_id"],
                view["bundle_id"],
                view["patches"],
                format_status_card(view["status"], view["message"]),
                format_review_meta(view["source"], len(view["patches"])),
                gr.update(choices=choices, value=first, interactive=pending),
                gr.update(
                    choices=choices,
                    value=view["selected_patch_ids"],
                    interactive=pending,
                ),
                view["diff"],
                gr.update(value="", interactive=pending),
                gr.update(interactive=pending),
                gr.update(interactive=pending),
                gr.update(interactive=pending),
            )

        outputs = [
            thread_id,
            bundle_state,
            patches_state,
            status,
            review_meta,
            patch_picker,
            selected_patches,
            diff,
            note,
            accept_all,
            accept_selected,
            reject_all,
        ]

        def start_view(task_query):
            return render(controller.start(task_query))

        def reload_view(current_thread_id):
            return render(controller.reload(current_thread_id))

        def accept_all_view(current_thread_id, bundle_id, approval_note):
            return render(controller.accept_all(current_thread_id, bundle_id, approval_note))

        def reject_all_view(current_thread_id, bundle_id, approval_note):
            return render(controller.reject_all(current_thread_id, bundle_id, approval_note))

        def accept_selected_view(
            current_thread_id,
            bundle_id,
            patch_ids,
            approval_note,
        ):
            return render(
                controller.accept_selected(
                    current_thread_id,
                    bundle_id,
                    patch_ids,
                    approval_note,
                )
            )

        start_button.click(start_view, query, outputs)
        query.submit(start_view, query, outputs)
        reload_button.click(reload_view, thread_id, outputs)
        patch_picker.change(select_patch_diff, [patches_state, patch_picker], diff)
        accept_all.click(
            accept_all_view,
            [thread_id, bundle_state, note],
            outputs,
        )
        reject_all.click(
            reject_all_view,
            [thread_id, bundle_state, note],
            outputs,
        )
        accept_selected.click(
            accept_selected_view,
            [thread_id, bundle_state, selected_patches, note],
            outputs,
        )

    return demo.queue(default_concurrency_limit=1)

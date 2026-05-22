from __future__ import annotations

from app.services.audit_chat_runtime.bridge import AuditChatRuntimeModelClient
from app.services.audit_chat_runtime.prompts import AUDIT_CHAT_SYSTEM_PROMPT
from app.services.finding_runtime.models import RuntimeMessageRole, TranscriptItem
from app.services.runtime_core.tool_message_codec import ToolMessageFormat


def test_audit_chat_model_messages_omit_recon_payload_and_finding_finalizer_reminder():
    messages = AuditChatRuntimeModelClient._build_messages(
        system_prompt=AUDIT_CHAT_SYSTEM_PROMPT,
        recon_payload={"project_info": {"workspace_root": "/tmp/secret-workspace"}},
        transcript=[TranscriptItem(role=RuntimeMessageRole.USER, content="继续解释上述漏洞")],
        tool_definitions=[
            {
                "name": "Read",
                "description": "Read files",
                "input_schema": {"type": "object"},
            }
        ],
        tool_message_format=ToolMessageFormat.OPENAI_TOOLS,
    )

    system = messages[0]["content"]
    assert "Runtime recon payload" not in system
    assert "/tmp/secret-workspace" not in system
    assert "FinalizeFinding" not in system
    assert "FinalizeVulnerabilityReports" not in system
    assert "默认始终使用中文回复用户" in system


def test_audit_chat_system_prompt_is_general_chat_not_fixed_finding_flow():
    assert "你不是固定流程的 Finding Agent" in AUDIT_CHAT_SYSTEM_PROMPT
    assert "不再需要调用工具时，应自然结束本轮回复" in AUDIT_CHAT_SYSTEM_PROMPT
    assert "复盘漏洞发现过程" in AUDIT_CHAT_SYSTEM_PROMPT
    assert "生成、重写、翻译或改进漏洞报告" in AUDIT_CHAT_SYSTEM_PROMPT

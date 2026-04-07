"""Lazy exports for the agent service package."""

__all__ = [
    "EventManager",
    "AgentEventEmitter",
    "BaseAgent",
    "AgentConfig",
    "AgentResult",
    "OrchestratorAgent",
    "ReconAgent",
    "AnalysisAgent",
    "VerificationAgent",
    "AgentState",
    "AgentStatus",
    "AgentRegistry",
    "agent_registry",
    "AgentMessage",
    "MessageType",
    "MessagePriority",
    "MessageBus",
    "KnowledgeLoader",
    "knowledge_loader",
    "get_available_modules",
    "get_module_content",
    "SecurityKnowledgeRAG",
    "security_knowledge_rag",
    "SecurityKnowledgeQueryTool",
    "GetVulnerabilityKnowledgeTool",
    "ThinkTool",
    "ReflectTool",
    "CreateVulnerabilityReportTool",
    "FinishScanTool",
    "CreateSubAgentTool",
    "SendMessageTool",
    "ViewAgentGraphTool",
    "WaitForMessageTool",
    "AgentFinishTool",
    "Tracer",
    "get_global_tracer",
    "set_global_tracer",
]


def __getattr__(name: str):
    if name in {"EventManager", "AgentEventEmitter"}:
        from .event_manager import AgentEventEmitter, EventManager

        return {"EventManager": EventManager, "AgentEventEmitter": AgentEventEmitter}[name]
    if name in {"BaseAgent", "AgentConfig", "AgentResult", "OrchestratorAgent", "ReconAgent", "AnalysisAgent", "VerificationAgent"}:
        from .agents import AnalysisAgent, AgentConfig, AgentResult, BaseAgent, OrchestratorAgent, ReconAgent, VerificationAgent

        mapping = {
            "BaseAgent": BaseAgent,
            "AgentConfig": AgentConfig,
            "AgentResult": AgentResult,
            "OrchestratorAgent": OrchestratorAgent,
            "ReconAgent": ReconAgent,
            "AnalysisAgent": AnalysisAgent,
            "VerificationAgent": VerificationAgent,
        }
        return mapping[name]
    if name in {"AgentState", "AgentStatus", "AgentRegistry", "agent_registry", "AgentMessage", "MessageType", "MessagePriority", "MessageBus"}:
        from .core import AgentMessage, AgentRegistry, AgentState, AgentStatus, MessageBus, MessagePriority, MessageType, agent_registry

        mapping = {
            "AgentState": AgentState,
            "AgentStatus": AgentStatus,
            "AgentRegistry": AgentRegistry,
            "agent_registry": agent_registry,
            "AgentMessage": AgentMessage,
            "MessageType": MessageType,
            "MessagePriority": MessagePriority,
            "MessageBus": MessageBus,
        }
        return mapping[name]
    if name in {
        "KnowledgeLoader",
        "knowledge_loader",
        "get_available_modules",
        "get_module_content",
        "SecurityKnowledgeRAG",
        "security_knowledge_rag",
        "SecurityKnowledgeQueryTool",
        "GetVulnerabilityKnowledgeTool",
    }:
        from .knowledge import (
            GetVulnerabilityKnowledgeTool,
            KnowledgeLoader,
            SecurityKnowledgeQueryTool,
            SecurityKnowledgeRAG,
            get_available_modules,
            get_module_content,
            knowledge_loader,
            security_knowledge_rag,
        )

        mapping = {
            "KnowledgeLoader": KnowledgeLoader,
            "knowledge_loader": knowledge_loader,
            "get_available_modules": get_available_modules,
            "get_module_content": get_module_content,
            "SecurityKnowledgeRAG": SecurityKnowledgeRAG,
            "security_knowledge_rag": security_knowledge_rag,
            "SecurityKnowledgeQueryTool": SecurityKnowledgeQueryTool,
            "GetVulnerabilityKnowledgeTool": GetVulnerabilityKnowledgeTool,
        }
        return mapping[name]
    if name in {"ThinkTool", "ReflectTool", "CreateVulnerabilityReportTool", "FinishScanTool", "CreateSubAgentTool", "SendMessageTool", "ViewAgentGraphTool", "WaitForMessageTool", "AgentFinishTool"}:
        from .tools import (
            AgentFinishTool,
            CreateSubAgentTool,
            CreateVulnerabilityReportTool,
            FinishScanTool,
            ReflectTool,
            SendMessageTool,
            ThinkTool,
            ViewAgentGraphTool,
            WaitForMessageTool,
        )

        mapping = {
            "ThinkTool": ThinkTool,
            "ReflectTool": ReflectTool,
            "CreateVulnerabilityReportTool": CreateVulnerabilityReportTool,
            "FinishScanTool": FinishScanTool,
            "CreateSubAgentTool": CreateSubAgentTool,
            "SendMessageTool": SendMessageTool,
            "ViewAgentGraphTool": ViewAgentGraphTool,
            "WaitForMessageTool": WaitForMessageTool,
            "AgentFinishTool": AgentFinishTool,
        }
        return mapping[name]
    if name in {"Tracer", "get_global_tracer", "set_global_tracer"}:
        from .telemetry import Tracer, get_global_tracer, set_global_tracer

        return {"Tracer": Tracer, "get_global_tracer": get_global_tracer, "set_global_tracer": set_global_tracer}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
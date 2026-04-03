from langgraph.graph import StateGraph, END
from agents.state import VerificationState
from agents.extraction_agent import extraction_agent
from agents.forgery_agent import forgery_detection_agent
from agents.kyc_agent import kyc_agent
from agents.decision_agent import decision_support_agent
from utils.logger import make_log


def should_continue_after_extraction(state: VerificationState) -> str:
    """Route after extraction — skip rest if error."""
    if state.get("error") or not state.get("extracted_fields"):
        return "end"
    return "continue"


def build_verification_graph():
    """Build and compile the LangGraph verification workflow."""
    workflow = StateGraph(VerificationState)

    # Add nodes
    workflow.add_node("extraction", extraction_agent)
    workflow.add_node("forgery_detection", forgery_detection_agent)
    workflow.add_node("kyc_verification", kyc_agent)
    workflow.add_node("decision_support", decision_support_agent)

    # Entry point
    workflow.set_entry_point("extraction")

    # Conditional routing after extraction
    workflow.add_conditional_edges(
        "extraction",
        should_continue_after_extraction,
        {
            "continue": "forgery_detection",
            "end": END,
        },
    )

    # Run forgery and KYC in sequence (LangGraph doesn't natively parallel without send API)
    workflow.add_edge("forgery_detection", "kyc_verification")
    workflow.add_edge("kyc_verification", "decision_support")
    workflow.add_edge("decision_support", END)

    return workflow.compile()


# Singleton graph instance
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_verification_graph()
    return _graph


def run_verification(document_name: str, document_base64: str) -> VerificationState:
    """Run the full verification pipeline on a document."""
    graph = get_graph()

    initial_state: VerificationState = {
        "document_name": document_name,
        "document_base64": document_base64,
        "document_type": "Unknown",
        "extracted_fields": {},
        "forgery_results": {},
        "kyc_results": {},
        "decision_results": {},
        "final_results": {},
        "overall_verdict": "PENDING",
        "overall_confidence": 0.0,
        "overall_summary": "",
        "human_review_fields": [],
        "human_reviews": {},
        "logs": [make_log("Orchestrator", "WORKFLOW_START",
                          f"Starting verification pipeline for document: {document_name}")],
        "error": None,
        "current_step": "init",
    }

    result = graph.invoke(initial_state)
    result["logs"].append(
        make_log("Orchestrator", "WORKFLOW_COMPLETE",
                 f"Verification pipeline complete. Verdict: {result.get('overall_verdict', 'N/A')}",
                 "SUCCESS" if result.get("overall_verdict") == "APPROVED" else "WARNING")
    )
    return result

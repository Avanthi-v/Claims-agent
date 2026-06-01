from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict
import uuid

from backend.agents.graph import app_graph

app = FastAPI(title="Claims State Graph API")


@app.get("/health")
def health_check():
    return {"status": "ok"}


class ClaimSubmission(BaseModel):
    member_id: str
    claim_id: str
    estimated_cost: float


class Approval(BaseModel):
    thread_id: str
    approved: bool


def _serialize_messages(messages: Any) -> Any:
    if messages is None:
        return []
    serialized = []
    for m in messages:
        # BaseMessage-like objects have `content` attribute
        if hasattr(m, "content"):
            serialized.append(getattr(m, "content"))
        else:
            serialized.append(str(m))
    return serialized


def _serialize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not state:
        return out
    for k, v in state.items():
        if k == "messages":
            out[k] = _serialize_messages(v)
        else:
            out[k] = v
    return out


@app.post("/submit")
async def submit(claim: ClaimSubmission):
    thread_id = f"claim_{uuid.uuid4().hex}"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "claim_id": claim.claim_id,
        "member_id": claim.member_id,
        "estimated_cost": claim.estimated_cost,
        "member_verified": False,
        "underwriting_score": 0,
        "human_approved": False,
        "status": "Initiated",
        "messages": [],
    }

    current_state = dict(initial_state)
    interrupted = False

    # Stream until the graph yields an interrupt (e.g., paused for human review)
    for step in app_graph.stream(initial_state, config=config):
        if "__interrupt__" in step:
            interrupted = True
            break
        for node_result in step.values():
            if isinstance(node_result, dict):
                # merge state updates
                current_state.update(node_result)

    # Try to get canonical snapshot from the graph
    try:
        snapshot = app_graph.get_state(config)
        values = getattr(snapshot, "values", current_state)
    except Exception:
        values = current_state

    return {"thread_id": thread_id, "interrupted": interrupted, "state": _serialize_state(values)}


@app.post("/approve")
async def approve(payload: Approval):
    config = {"configurable": {"thread_id": payload.thread_id}}

    # Apply manager decision to the graph state
    try:
        config = app_graph.update_state(config, {"human_approved": payload.approved})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update state: {e}")

    current_state: Dict[str, Any] = {}
    # Resume execution until completion
    for step in app_graph.stream(None, config=config):
        if "__interrupt__" in step:
            # should not hit another interrupt in this simple graph, but skip if it does
            continue
        for node_result in step.values():
            if isinstance(node_result, dict):
                current_state.update(node_result)

    try:
        snapshot = app_graph.get_state(config)
        values = getattr(snapshot, "values", current_state)
    except Exception:
        values = current_state

    return {"thread_id": payload.thread_id, "state": _serialize_state(values)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

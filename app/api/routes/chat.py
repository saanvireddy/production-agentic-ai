from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, status

from app.agents.graph import run_agent
from app.api.deps import get_container, get_current_user, rate_limit
from app.api.schemas import ChatRequest, ChatResponse
from app.auth.users import User
from app.services.container import Container

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse, summary="Ask the agent a question")
def chat(
    body: ChatRequest, user: User = Depends(rate_limit), container: Container = Depends(get_container)
) -> ChatResponse:
    session_id = body.session_id or str(uuid.uuid4())
    history = container.memory.history(user.username, session_id)

    # Only first-turn questions are cacheable: follow-ups depend on the conversation.
    cached = container.cache.get(body.question) if not history else None
    if cached:
        resp = ChatResponse(**{**cached, "session_id": session_id, "cached": True})
    else:
        state = run_agent(container.agent, body.question, history)
        resp = ChatResponse(
            session_id=session_id,
            answer=state["answer"],
            route=state["route"],
            route_method=state.get("route_method", ""),
            standalone_question=state.get("standalone_question", body.question),
            sources=state.get("sources") or [],
            sql=state.get("sql"),
            rows=state.get("rows") or [],
            validation=state.get("validation") or {},
            latency_ms=state.get("latency_ms") or {},
        )
        if not history and resp.route in {"rag", "sql"} and resp.validation.get("passed"):
            container.cache.set(body.question, resp.model_dump(exclude={"session_id", "cached"}))

    container.memory.append(user.username, session_id, body.question, resp.answer)
    container.audit.log(
        session_id, user.username, body.question, resp.answer, resp.route, int(resp.latency_ms.get("total", 0))
    )
    logger.info("chat answered", extra={"route": resp.route, "cached": resp.cached, "user": user.username})
    return resp


@router.get("/{session_id}/history", summary="Conversation history for a session")
def history(
    session_id: str, user: User = Depends(get_current_user), container: Container = Depends(get_container)
) -> list[dict[str, str]]:
    return container.memory.history(user.username, session_id)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Clear a conversation")
def clear(
    session_id: str, user: User = Depends(get_current_user), container: Container = Depends(get_container)
) -> None:
    container.memory.clear(user.username, session_id)

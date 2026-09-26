"""Streamlit front-end for the Agentic AI platform. Talks to the API only (no direct DB access).

API_URL=http://localhost:8000 streamlit run ui/streamlit_app.py
"""

from __future__ import annotations

import os
import uuid

import httpx
import pandas as pd
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
ROUTE_LABEL = {"rag": "📄 Policy documents (RAG)", "sql": "🗄️ Employee database (SQL)", "general": "💬 General"}

st.set_page_config(page_title="AI Knowledge & Analytics", page_icon="🧭", layout="wide")


def api() -> httpx.Client:
    headers = {"Authorization": f"Bearer {st.session_state.token}"} if st.session_state.get("token") else {}
    return httpx.Client(base_url=API_URL, headers=headers, timeout=180)


# ---------------- Sidebar: auth + session ----------------
with st.sidebar:
    st.header("🔐 Sign in")
    if not st.session_state.get("token"):
        with st.form("login"):
            username = st.text_input("Username", value="admin")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log in", use_container_width=True):
                r = httpx.post(f"{API_URL}/api/v1/auth/login", json={"username": username, "password": password})
                if r.status_code == 200:
                    st.session_state.token = r.json()["access_token"]
                    st.session_state.username = username
                    st.rerun()
                else:
                    st.error("Invalid credentials")
    else:
        st.success(f"Signed in as **{st.session_state.username}**")
        if st.button("Log out", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    st.divider()
    st.caption("Conversation")
    st.session_state.setdefault("session_id", str(uuid.uuid4()))
    st.session_state.setdefault("messages", [])
    if st.button("New conversation", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()
    show_debug = st.toggle("Show retrieved chunks & SQL", value=True)

    if st.session_state.get("token"):
        st.divider()
        st.caption("Knowledge base")
        try:
            docs = api().get("/api/v1/documents").json()
            for d in docs:
                st.write(f"• {d['filename']} ({d['num_pages']} p, {d['num_chunks']} chunks)")
        except Exception:  # noqa: BLE001
            st.warning("API unreachable")

    st.divider()
    st.caption("Try asking")
    for ex in [
        "What is the company's remote work policy?",
        "How many employees are in Engineering?",
        "What about Finance?",
        "Compare Engineering and Finance headcount.",
        "What is the vacation policy for employees with more than 5 years of experience?",
        "Delete all employees",
    ]:
        st.code(ex, language=None)

# ---------------- Main: chat ----------------
st.title("🧭 AI Knowledge & Analytics")
st.caption("Agentic RAG + SQL over Helix Dynamics policies and HR data (fictional company).")

if not st.session_state.get("token"):
    st.info("Sign in from the sidebar to start.")
    st.stop()


def render_meta(m: dict) -> None:
    cols = st.columns(4)
    cols[0].caption(ROUTE_LABEL.get(m["route"], m["route"]))
    cols[1].caption(f"⏱️ {m['latency_ms'].get('total', 0) / 1000:.2f}s" + (" · cached" if m.get("cached") else ""))
    v = m.get("validation") or {}
    cols[2].caption("✅ guardrails passed" if v.get("passed") else "⚠️ guardrails flagged")
    if m.get("standalone_question") and m["standalone_question"] != m.get("question"):
        cols[3].caption(f"↪️ interpreted as: *{m['standalone_question']}*")

    if m["route"] == "rag" and m["sources"]:
        st.markdown("**Sources:** " + "; ".join(f"`{s['source']}` p.{s['page']}" for s in m["sources"]))
    if m["route"] == "sql" and m.get("sql"):
        st.markdown("**Source:** employee database")

    if show_debug:
        if m["route"] == "rag" and m["sources"]:
            with st.expander("Retrieved chunks"):
                for s in m["sources"]:
                    st.markdown(f"**{s['source']}**, page {s['page']} · score {s['score']}")
                    st.text(s["snippet"])
        if m.get("sql"):
            with st.expander("Generated SQL & result"):
                st.code(m["sql"], language="sql")
                if m.get("rows"):
                    st.dataframe(pd.DataFrame(m["rows"]), use_container_width=True, hide_index=True)
        with st.expander("Latency breakdown & validation"):
            st.json({"latency_ms": m["latency_ms"], "validation": v, "route_method": m.get("route_method")})


for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m["role"] == "assistant" and "meta" in m:
            render_meta(m["meta"])

if prompt := st.chat_input("Ask about policies or HR analytics..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"), st.spinner("Thinking..."):
        r = api().post("/api/v1/chat", json={"question": prompt, "session_id": st.session_state.session_id})
        if r.status_code == 401:
            st.session_state.pop("token", None)
            st.error("Session expired, please log in again.")
            st.stop()
        if r.status_code == 429:
            st.error("Rate limit reached, wait a minute and retry.")
            st.stop()
        r.raise_for_status()
        meta = {**r.json(), "question": prompt}
        st.markdown(meta["answer"])
        render_meta(meta)
    st.session_state.messages.append({"role": "assistant", "content": meta["answer"], "meta": meta})

import pytest

from app.rag.ingestion import chunk_pages, clean_text, ingest_bytes
from app.rag.pipeline import NO_ANSWER, RagTool
from app.rag.vectorstore import InMemoryVectorStore
from app.services.llm import DeterministicFakeLLM


@pytest.mark.parametrize(
    "question,source",
    [
        ("What is the company's remote work policy?", "remote_work_policy.pdf"),
        ("How many vacation days do employees with more than 5 years get?", "leave_policy.pdf"),
        ("What is the 401(k) match?", "benefits_policy.pdf"),
        ("What is the minimum password length?", "security_policy.pdf"),
    ],
)
def test_relevant_question_retrieves_relevant_document(vector_store, embeddings, question, source):
    hits = RagTool(vector_store, embeddings, DeterministicFakeLLM()).retrieve(question, k=3)
    assert hits[0].source == source


def test_rag_answer_has_page_citation(vector_store, embeddings):
    res = RagTool(vector_store, embeddings, DeterministicFakeLLM()).run("How many days per week can I work remotely?")
    assert res.grounded
    assert res.sources[0].source == "remote_work_policy.pdf"
    assert res.sources[0].page == 2
    assert res.sources[0].citation() == "remote_work_policy.pdf, page 2"


def test_rag_refuses_without_relevant_context(embeddings):
    res = RagTool(InMemoryVectorStore(), embeddings, DeterministicFakeLLM()).run("What is the travel policy?")
    assert res.answer == NO_ANSWER
    assert not res.grounded


def test_ingestion_is_idempotent(embeddings):
    store = InMemoryVectorStore()
    data = b"# Parking Policy\n\nEmployees can park in lot B for free."
    assert ingest_bytes("parking.md", data, store, embeddings).status == "ingested"
    assert ingest_bytes("parking.md", data, store, embeddings).status == "unchanged"
    assert ingest_bytes("parking.md", data + b" Updated.", store, embeddings).status == "ingested"


def test_ingestion_rejects_unsupported_types(embeddings):
    with pytest.raises(ValueError):
        ingest_bytes("malware.exe", b"MZ...", InMemoryVectorStore(), embeddings)


def test_ingestion_strips_client_path(embeddings):
    store = InMemoryVectorStore()
    ingest_bytes("../../etc/notes.txt", b"hello world policy", store, embeddings)
    assert [d.filename for d in store.list_documents()] == ["notes.txt"]


def test_chunks_keep_page_numbers():
    chunks = chunk_pages(["page one text", "", "page three text"], "T")
    assert [c.page for c in chunks] == [1, 3]


def test_clean_text():
    assert clean_text("remote-\nwork   policy\n\n\n\nend") == "remotework policy\n\nend"

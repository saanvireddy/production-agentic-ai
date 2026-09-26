from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_container, get_current_user, require_admin
from app.api.schemas import DocumentOut, IngestResponse
from app.auth.users import User
from app.rag.ingestion import MAX_UPLOAD_BYTES, ingest_bytes
from app.services.container import Container

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a document (admin)",
)
async def upload(
    file: UploadFile = File(...), user: User = Depends(require_admin), container: Container = Depends(get_container)
) -> IngestResponse:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        res = ingest_bytes(file.filename or "upload", data, container.store, container.embeddings, user.username)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    if res.status == "ingested":
        container.cache.invalidate_all()
    return IngestResponse(**res.__dict__)


@router.get("", response_model=list[DocumentOut], summary="List ingested documents")
def list_documents(
    _: User = Depends(get_current_user), container: Container = Depends(get_container)
) -> list[DocumentOut]:
    return [DocumentOut(**d.__dict__) for d in container.store.list_documents()]


@router.delete("/{filename}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a document (admin)")
def delete_document(
    filename: str, _: User = Depends(require_admin), container: Container = Depends(get_container)
) -> None:
    if not container.store.delete_document(filename):
        raise HTTPException(status_code=404, detail="Document not found")
    container.cache.invalidate_all()

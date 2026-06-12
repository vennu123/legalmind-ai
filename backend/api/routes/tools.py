from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from agent_tools.answer_question import answer_question
from agent_tools.check_compliance import check_compliance
from agent_tools.compare_documents import compare_documents
from agent_tools.document_tools import (
    check_document_compliance,
    compare_selected_documents,
    extract_document_entities,
    summarize_document,
)
from agent_tools.extract_entities import extract_entities
from agent_tools.search_document import search_document
from agent_tools.summarize_section import summarize_section
from core.auth import CurrentUser, get_current_user


router = APIRouter(prefix="/tools", tags=["tools"])


class SearchDocumentRequest(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=20)
    document_ids: list[str] | None = None


class SummarizeSectionRequest(BaseModel):
    section_text: str


class ExtractEntitiesRequest(BaseModel):
    section_text: str


class CheckComplianceRequest(BaseModel):
    clause_text: str
    clause_type: str = "general"


class CompareDocumentsRequest(BaseModel):
    first_text: str
    second_text: str


class AnswerQuestionRequest(BaseModel):
    question: str
    limit: int = Field(default=5, ge=1, le=20)
    document_ids: list[str] | None = None


class SummarizeDocumentRequest(BaseModel):
    query: str = "Summarize this document"
    limit: int = Field(default=10, ge=1, le=30)
    document_ids: list[str] | None = None


class ExtractDocumentEntitiesRequest(BaseModel):
    query: str = "parties dates money obligations deadlines"
    limit: int = Field(default=10, ge=1, le=30)
    document_ids: list[str] | None = None


class CheckDocumentComplianceRequest(BaseModel):
    query: str
    clause_type: str = "general"
    limit: int = Field(default=10, ge=1, le=30)
    document_ids: list[str] | None = None


class CompareSelectedDocumentsRequest(BaseModel):
    query: str
    document_ids: list[str]
    limit_per_document: int = Field(default=5, ge=1, le=20)


@router.post("/search-document")
async def search_document_tool(
    request: SearchDocumentRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    results = search_document(
        request.query,
        request.limit,
        request.document_ids,
        user_id=current_user.user_id,
    )

    return {
        "query": request.query,
        "document_ids": request.document_ids or [],
        "result_count": len(results),
        "results": results,
    }


@router.post("/summarize-section")
async def summarize_section_tool(request: SummarizeSectionRequest):
    return summarize_section(request.section_text)


@router.post("/extract-entities")
async def extract_entities_tool(request: ExtractEntitiesRequest):
    return extract_entities(request.section_text)


@router.post("/check-compliance")
async def check_compliance_tool(request: CheckComplianceRequest):
    return check_compliance(request.clause_text, request.clause_type)


@router.post("/compare-documents")
async def compare_documents_tool(request: CompareDocumentsRequest):
    return compare_documents(request.first_text, request.second_text)


@router.post("/answer-question")
async def answer_question_tool(
    request: AnswerQuestionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return answer_question(
        request.question,
        request.limit,
        request.document_ids,
        user_id=current_user.user_id,
    )


@router.post("/summarize-document")
async def summarize_document_tool(
    request: SummarizeDocumentRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return summarize_document(
        request.query,
        request.limit,
        request.document_ids,
        user_id=current_user.user_id,
    )


@router.post("/extract-document-entities")
async def extract_document_entities_tool(
    request: ExtractDocumentEntitiesRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return extract_document_entities(
        request.query,
        request.limit,
        request.document_ids,
        user_id=current_user.user_id,
    )


@router.post("/check-document-compliance")
async def check_document_compliance_tool(
    request: CheckDocumentComplianceRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return check_document_compliance(
        request.query,
        request.clause_type,
        request.limit,
        request.document_ids,
        user_id=current_user.user_id,
    )


@router.post("/compare-selected-documents")
async def compare_selected_documents_tool(
    request: CompareSelectedDocumentsRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return compare_selected_documents(
        request.query,
        request.document_ids,
        request.limit_per_document,
        user_id=current_user.user_id,
    )

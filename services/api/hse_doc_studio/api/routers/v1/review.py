"""Ревью-комментарии к тексту файлов проекта: треды, ответы, статус, упоминания (серверный режим)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.schemas import review as s
from hse_doc_studio.core.review.entities import Anchor, PdfAnchor, PdfPlace, PdfRect, ReviewThread, ThreadStatus
from hse_doc_studio.use_cases.review.pdf_threads import CreatePdfReviewThreadUC, ListDocumentReviewUC, NewPdfThread
from hse_doc_studio.use_cases.review.threads import (
    CreateReviewThreadUC,
    DeleteReviewCommentUC,
    EditReviewCommentUC,
    ListMentionCandidatesUC,
    ListReviewThreadsUC,
    NewThread,
    ReplyReviewThreadUC,
    SetReviewThreadStatusUC,
)

router = APIRouter(dependencies=[Depends(require_server_mode)])


async def _get[T](request: Request, kind: type[T]) -> T:
    return await request.state.dishka_container.get(kind)


def _rects(rects: tuple[PdfRect, ...]) -> list[s.PdfRectModel]:
    return [s.PdfRectModel(x=r.x, y=r.y, width=r.width, height=r.height) for r in rects]


def _anchor_model(thread: ReviewThread) -> s.AnchorModel | s.PdfAnchorModel:
    anchor = thread.anchor
    if isinstance(anchor, PdfAnchor):
        return s.PdfAnchorModel(
            kind="pdf",
            doc_id=anchor.doc_id,
            page=anchor.page,
            rects=_rects(anchor.rects),
            text=anchor.text,
            build_sha=anchor.build_sha,
        )
    return s.AnchorModel(
        quote=anchor.quote, prefix=anchor.prefix, suffix=anchor.suffix, start=anchor.start, end=anchor.end
    )


def _place_model(place: PdfPlace | None) -> s.PdfPlaceModel | None:
    if place is None:
        return None
    return s.PdfPlaceModel(page=place.page, rects=_rects(place.rects), text=place.text, exact=place.exact)


def thread_model(thread: ReviewThread) -> s.ThreadModel:
    return s.ThreadModel(
        id=thread.id,
        path=thread.path,
        anchor=_anchor_model(thread),
        status=thread.status.value,
        created_by=thread.created_by,
        created_by_name=thread.created_by_name,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        resolved_by_name=thread.resolved_by_name,
        resolved_at=thread.resolved_at,
        comments=[
            s.CommentModel(
                id=c.id,
                author_id=c.author_id,
                author_name=c.author_name,
                body=c.body,
                mentions=list(c.mentions),
                created_at=c.created_at,
                edited_at=c.edited_at,
            )
            for c in thread.comments
        ],
    )


@router.get("/projects/{project_id}/review/threads", response_model=s.ThreadList)
async def list_threads(
    project_id: UUID,
    request: Request,
    response: Response,
    path: Annotated[str | None, Query(max_length=512)] = None,
    status_filter: Annotated[s.ThreadStatusName | None, Query(alias="status")] = None,
) -> s.ThreadList:
    response.headers["Cache-Control"] = "no-store"
    uc = await _get(request, ListReviewThreadsUC)
    found = await uc.execute(project_id, path=path, status=ThreadStatus(status_filter) if status_filter else None)
    return s.ThreadList(items=[thread_model(t) for t in found])


@router.post("/projects/{project_id}/review/threads", response_model=s.ThreadModel, status_code=status.HTTP_201_CREATED)
async def create_thread(project_id: UUID, body: s.CreateThreadRequest, request: Request) -> s.ThreadModel:
    uc = await _get(request, CreateReviewThreadUC)
    a = body.anchor
    thread = await uc.execute(
        project_id,
        NewThread(
            path=body.path,
            anchor=Anchor(quote=a.quote, prefix=a.prefix, suffix=a.suffix, start=a.start, end=a.end),
            body=body.body,
            mentions=tuple(body.mentions),
        ),
    )
    return thread_model(thread)


@router.post(
    "/projects/{project_id}/review/threads/{thread_id}/comments",
    response_model=s.ThreadModel,
    status_code=status.HTTP_201_CREATED,
)
async def reply(project_id: UUID, thread_id: str, body: s.ReplyRequest, request: Request) -> s.ThreadModel:
    uc = await _get(request, ReplyReviewThreadUC)
    return thread_model(await uc.execute(project_id, thread_id, body.body, tuple(body.mentions)))


@router.put("/projects/{project_id}/review/threads/{thread_id}/status", response_model=s.ThreadModel)
async def set_status(project_id: UUID, thread_id: str, body: s.SetStatusRequest, request: Request) -> s.ThreadModel:
    uc = await _get(request, SetReviewThreadStatusUC)
    return thread_model(await uc.execute(project_id, thread_id, ThreadStatus(body.status)))


@router.patch("/projects/{project_id}/review/comments/{comment_id}", response_model=s.ThreadModel)
async def edit_comment(
    project_id: UUID, comment_id: str, body: s.EditCommentRequest, request: Request
) -> s.ThreadModel:
    uc = await _get(request, EditReviewCommentUC)
    return thread_model(await uc.execute(project_id, comment_id, body.body))


@router.delete("/projects/{project_id}/review/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(project_id: UUID, comment_id: str, request: Request) -> Response:
    uc = await _get(request, DeleteReviewCommentUC)
    await uc.execute(project_id, comment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/review/mentions", response_model=s.MentionCandidateList)
async def mention_candidates(
    project_id: UUID,
    request: Request,
    response: Response,
    q: Annotated[str, Query(max_length=100)] = "",
) -> s.MentionCandidateList:
    response.headers["Cache-Control"] = "no-store"
    uc = await _get(request, ListMentionCandidatesUC)
    found = await uc.execute(project_id, q)
    return s.MentionCandidateList(
        items=[s.MentionCandidateModel(user_id=c.user_id, name=c.name, detail=c.detail) for c in found]
    )


@router.post(
    "/projects/{project_id}/review/pdf-threads", response_model=s.ThreadModel, status_code=status.HTTP_201_CREATED
)
async def create_pdf_thread(project_id: UUID, body: s.CreatePdfThreadRequest, request: Request) -> s.ThreadModel:
    """Тред из превью PDF: по возможности к исходнику (SyncTeX и поиск текста), иначе к месту в PDF."""
    uc = await _get(request, CreatePdfReviewThreadUC)
    thread = await uc.execute(
        project_id,
        NewPdfThread(
            doc_id=body.doc_id,
            page=body.page,
            rects=tuple(PdfRect(x=r.x, y=r.y, width=r.width, height=r.height) for r in body.rects),
            text=body.text,
            body=body.body,
            mentions=tuple(body.mentions),
        ),
    )
    return thread_model(thread)


@router.get("/projects/{project_id}/review/documents/{doc_id}", response_model=s.DocumentReviewModel)
async def document_review(project_id: UUID, doc_id: str, request: Request, response: Response) -> s.DocumentReviewModel:
    """Треды документа для превью и их места на текущем PDF."""
    response.headers["Cache-Control"] = "no-store"
    uc = await _get(request, ListDocumentReviewUC)
    found = await uc.execute(project_id, doc_id)
    return s.DocumentReviewModel(
        build_sha=found.build_sha,
        items=[s.PlacedThreadModel(thread=thread_model(i.thread), place=_place_model(i.place)) for i in found.items],
    )

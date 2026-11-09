"""审核台：待审列表、通过、删除、撤销。A-21 / A-22。"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import db, errors
from ..deps import current_user, require_admin

router = APIRouter(prefix="/api/v1/admin/review", tags=["审核台"])


class ReviewIn(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    remark: str | None = Field(default=None, max_length=200)


def _write_log(operator_id: int, post_id: int, action: int, remark: str | None):
    db.execute(
        "INSERT INTO review_log (target_type, target_id, operator_id, action, remark, "
        "created_at) VALUES (2,%s,%s,%s,%s,%s)",
        (post_id, operator_id, action, remark, datetime.now()))


@router.get("/tasks")
def tasks(page: int = 1, size: int = 20, user: dict = Depends(current_user)):
    require_admin(user)
    limit = max(1, min(size, 50))
    rows = db.query_all(
        "SELECT p.*, u.nickname, a.summary, a.sentiment, a.violation, a.confidence "
        "FROM post p LEFT JOIN `user` u ON u.id = p.author_id "
        "LEFT JOIN ai_result a ON a.post_id = p.id "
        "WHERE p.status = 1 ORDER BY p.id ASC LIMIT %s OFFSET %s",
        (limit, (max(1, page) - 1) * limit))
    return errors.ok([
        {
            "postId": r["id"],
            "title": r["title"],
            "excerpt": (r["body"] or "")[:60],
            "authorId": r["author_id"],
            "authorNickname": r.get("nickname"),
            "summary": r.get("summary"),
            "sentiment": r.get("sentiment"),
            "violation": bool(r.get("violation") or 0),
            "confidence": float(r["confidence"] or 0),
            "createdAt": r.get("created_at"),
        }
        for r in rows
    ])


@router.post("/{post_id}")
def review(post_id: int, body: ReviewIn, user: dict = Depends(current_user)):
    require_admin(user)
    post = db.query_one("SELECT * FROM post WHERE id=%s", (post_id,))
    if not post:
        raise errors.ApiError(errors.CODE_NOT_FOUND, "帖子不存在")
    if post["status"] != 1:
        raise errors.ApiError(errors.CODE_CONFLICT, "该内容不在待审状态")
    new_status = 0 if body.action == "approve" else 2
    db.execute("UPDATE post SET status=%s WHERE id=%s", (new_status, post_id))
    _write_log(user["id"], post_id, 1 if body.action == "approve" else 2, body.remark)
    return errors.ok()


@router.post("/{post_id}/undo")
def undo(post_id: int, user: dict = Depends(current_user)):
    """删除后 24 小时内可撤销，对应状态图 ⑥。"""
    require_admin(user)
    post = db.query_one("SELECT * FROM post WHERE id=%s", (post_id,))
    if not post:
        raise errors.ApiError(errors.CODE_NOT_FOUND, "帖子不存在")
    if post["status"] != 2:
        raise errors.ApiError(errors.CODE_CONFLICT, "只有已删除的内容可以撤销")
    last = db.query_one(
        "SELECT * FROM review_log WHERE target_type=2 AND target_id=%s AND action=2 "
        "ORDER BY id DESC LIMIT 1", (post_id,))
    if not last:
        raise errors.ApiError(errors.CODE_CONFLICT, "找不到删除记录，无法撤销")
    if last["created_at"] + timedelta(hours=24) < datetime.now():
        raise errors.ApiError(errors.CODE_FORBIDDEN, "已超过 24 小时撤销窗口")
    db.execute("UPDATE post SET status=0 WHERE id=%s", (post_id,))
    _write_log(user["id"], post_id, 3, "撤销处置")
    return errors.ok()

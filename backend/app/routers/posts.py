"""博客：板块、标签、帖子、回帖、点赞、收藏、AI 结果。A-12 ~ A-18。"""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from .. import db, errors
from ..deps import current_user

router = APIRouter(prefix="/api/v1", tags=["博客"])

# 敏感词：命中即置为待审（对应报告 8.3.3 表 27）
HARD_WORDS = ["代写", "代考", "赌博", "毒品", "枪", "色情", "诈骗"]
SOFT_WORDS = ["收费", "私聊报价", "包过", "内部渠道"]


class PostIn(BaseModel):
    boardId: int
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=20000)
    tagIds: list[int] = Field(default=[], max_length=5)


class ReplyIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    parentReplyId: int | None = None


class ToggleIn(BaseModel):
    liked: bool | None = None


def _excerpt(text: str | None, n: int = 80) -> str | None:
    if not text:
        return None
    return text if len(text) <= n else text[:n] + "…"


def _post_tags(post_ids: list[int]) -> dict[int, list[str]]:
    if not post_ids:
        return {}
    marks = ",".join(["%s"] * len(post_ids))
    rows = db.query_all(
        f"SELECT pt.post_id, t.name FROM post_tag pt JOIN tag t ON t.id=pt.tag_id "
        f"WHERE pt.post_id IN ({marks})", tuple(post_ids))
    out: dict[int, list[str]] = {}
    for r in rows:
        out.setdefault(r["post_id"], []).append(r["name"])
    return out


def _visible_post(post_id: int, user_id: int) -> dict:
    p = db.query_one("SELECT * FROM post WHERE id=%s", (post_id,))
    if not p:
        raise errors.ApiError(errors.CODE_NOT_FOUND, "帖子不存在")
    if p["status"] != 0 and p["author_id"] != user_id:
        raise errors.ApiError(errors.CODE_NOT_FOUND, "帖子不存在或未通过审核")
    return p


def _post_vo(p: dict, user_id: int, with_body: bool = True) -> dict:
    liked = db.query_one(
        "SELECT 1 AS x FROM like_record WHERE user_id=%s AND target_type=2 AND target_id=%s",
        (user_id, p["id"]))
    fav = db.query_one(
        "SELECT 1 AS x FROM favorite WHERE user_id=%s AND post_id=%s", (user_id, p["id"]))
    board = db.query_one("SELECT name FROM board WHERE id=%s", (p["board_id"],))
    author = db.query_one("SELECT nickname FROM `user` WHERE id=%s", (p["author_id"],))
    return {
        "id": p["id"],
        "boardId": p["board_id"],
        "boardName": board["name"] if board else None,
        "authorId": p["author_id"],
        "authorNickname": author["nickname"] if author else None,
        "title": p["title"],
        "body": p["body"] if with_body else None,
        "excerpt": _excerpt(p["body"]),
        "status": p["status"],
        "viewCount": p["view_count"],
        "likeCount": p["like_count"],
        "favoriteCount": p["favorite_count"],
        "createdAt": p.get("created_at"),
        "tags": _post_tags([p["id"]]).get(p["id"], []),
        "liked": bool(liked),
        "favorited": bool(fav),
    }


# ------------------------------------------------------------------ 基础数据
@router.get("/boards")
def boards(user: dict = Depends(current_user)):
    rows = db.query_all("SELECT * FROM board ORDER BY sort_no")
    return errors.ok([
        {"id": r["id"], "name": r["name"], "intro": r["intro"], "sortNo": r["sort_no"]}
        for r in rows
    ])


@router.get("/tags")
def tags(scope: int | None = None, user: dict = Depends(current_user)):
    sql = "SELECT * FROM tag"
    args: tuple = ()
    if scope is not None:
        sql += " WHERE scope=%s"
        args = (scope,)
    sql += " ORDER BY heat DESC, id ASC"
    rows = db.query_all(sql, args)
    return errors.ok([
        {"id": r["id"], "name": r["name"], "scope": r["scope"],
         "creatorId": r["creator_id"], "heat": r["heat"], "createdAt": r.get("created_at")}
        for r in rows
    ])


# ------------------------------------------------------------------ 帖子
def _run_ai(post_id: int) -> None:
    """后台任务：生成摘要、打标、违规判定。对应报告 UC-10。"""
    from .ai import analyze_post

    try:
        analyze_post(post_id)
    except Exception as exc:  # 模型不可用不能影响发帖
        print(f"AI 处理失败 post={post_id}: {exc}")


@router.get("/posts")
def list_posts(boardId: int | None = None, tagId: int | None = None,
               sort: str = "latest", page: int = 1, size: int = 20,
               user: dict = Depends(current_user)):
    sql = "SELECT * FROM post WHERE status=0"
    args: list = []
    if boardId is not None:
        sql += " AND board_id=%s"
        args.append(boardId)
    if tagId is not None:
        sql += " AND id IN (SELECT post_id FROM post_tag WHERE tag_id=%s)"
        args.append(tagId)
    order = "like_count DESC, view_count DESC" if sort == "hot" else "created_at DESC"
    limit = max(1, min(size, 50))
    sql += f" ORDER BY {order}, id DESC LIMIT %s OFFSET %s"
    args.extend([limit, (max(1, page) - 1) * limit])
    rows = db.query_all(sql, tuple(args))
    return errors.ok([_post_vo(p, user["id"], with_body=False) for p in rows])


@router.post("/posts")
def create_post(body: PostIn, background: BackgroundTasks,
                user: dict = Depends(current_user)):
    if not db.query_one("SELECT id FROM board WHERE id=%s", (body.boardId,)):
        raise errors.ApiError(errors.CODE_NOT_FOUND, "板块不存在")
    text = body.title + body.body
    pending = any(w in text for w in HARD_WORDS + SOFT_WORDS)
    now = datetime.now()
    post_id = db.execute(
        "INSERT INTO post (board_id, author_id, title, body, status, view_count, "
        "like_count, favorite_count, created_at) VALUES (%s,%s,%s,%s,%s,0,0,0,%s)",
        (body.boardId, user["id"], body.title, body.body, 1 if pending else 0, now),
    )
    for tag_id in body.tagIds:
        if db.query_one("SELECT id FROM tag WHERE id=%s", (tag_id,)):
            db.execute(
                "INSERT INTO post_tag (post_id, tag_id, source, created_at) VALUES (%s,%s,1,%s)",
                (post_id, tag_id, now),
            )
    background.add_task(_run_ai, post_id)     # 异步触发，不阻塞发布
    post = db.query_one("SELECT * FROM post WHERE id=%s", (post_id,))
    return errors.ok(_post_vo(post, user["id"]))


@router.get("/posts/{post_id}")
def post_detail(post_id: int, user: dict = Depends(current_user)):
    post = _visible_post(post_id, user["id"])
    db.execute("UPDATE post SET view_count = view_count + 1 WHERE id=%s", (post_id,))
    post["view_count"] += 1
    return errors.ok(_post_vo(post, user["id"]))


# ------------------------------------------------------------------ 回帖
@router.post("/posts/{post_id}/replies")
def add_reply(post_id: int, body: ReplyIn, user: dict = Depends(current_user)):
    post = _visible_post(post_id, user["id"])
    if post["status"] != 0:
        raise errors.ApiError(errors.CODE_FORBIDDEN, "该帖子不可回复")
    if body.parentReplyId:
        parent = db.query_one("SELECT * FROM reply WHERE id=%s", (body.parentReplyId,))
        if not parent or parent["post_id"] != post_id:
            raise errors.ApiError(errors.CODE_PARAM, "父回帖不属于该帖子")
    reply_id = db.execute(
        "INSERT INTO reply (post_id, author_id, parent_reply_id, content, like_count, "
        "status, created_at) VALUES (%s,%s,%s,%s,0,0,%s)",
        (post_id, user["id"], body.parentReplyId, body.content, datetime.now()),
    )
    row = db.query_one(
        "SELECT r.*, u.nickname FROM reply r LEFT JOIN `user` u ON u.id=r.author_id "
        "WHERE r.id=%s", (reply_id,))
    return errors.ok({
        "id": row["id"], "postId": row["post_id"], "authorId": row["author_id"],
        "authorNickname": row.get("nickname"), "parentReplyId": row["parent_reply_id"],
        "content": row["content"], "likeCount": row["like_count"],
        "createdAt": row.get("created_at"),
    })


@router.get("/posts/{post_id}/replies")
def list_replies(post_id: int, page: int = 1, size: int = 20,
                 user: dict = Depends(current_user)):
    if not db.query_one("SELECT id FROM post WHERE id=%s", (post_id,)):
        raise errors.ApiError(errors.CODE_NOT_FOUND, "帖子不存在")
    limit = max(1, min(size, 50))
    rows = db.query_all(
        "SELECT r.*, u.nickname FROM reply r LEFT JOIN `user` u ON u.id=r.author_id "
        "WHERE r.post_id=%s AND r.status=0 ORDER BY r.id ASC LIMIT %s OFFSET %s",
        (post_id, limit, (max(1, page) - 1) * limit))
    return errors.ok([
        {"id": r["id"], "postId": r["post_id"], "authorId": r["author_id"],
         "authorNickname": r.get("nickname"), "parentReplyId": r["parent_reply_id"],
         "content": r["content"], "likeCount": r["like_count"],
         "createdAt": r.get("created_at")}
        for r in rows
    ])


# ------------------------------------------------------------------ 互动
def _toggle_target(post_id: int) -> dict:
    p = db.query_one("SELECT * FROM post WHERE id=%s", (post_id,))
    if not p:
        raise errors.ApiError(errors.CODE_NOT_FOUND, "帖子不存在")
    if p["status"] != 0:
        raise errors.ApiError(errors.CODE_FORBIDDEN, "该帖子当前不可互动")
    return p


@router.post("/posts/{post_id}/like")
def toggle_like(post_id: int, body: ToggleIn | None = None,
                user: dict = Depends(current_user)):
    _toggle_target(post_id)
    want = True if body is None or body.liked is None else body.liked
    exists = db.query_one(
        "SELECT 1 AS x FROM like_record WHERE user_id=%s AND target_type=2 AND target_id=%s",
        (user["id"], post_id))
    if want and not exists:
        db.execute(
            "INSERT INTO like_record (user_id, target_type, target_id, created_at) "
            "VALUES (%s,2,%s,%s)", (user["id"], post_id, datetime.now()))
        db.execute("UPDATE post SET like_count = like_count + 1 WHERE id=%s", (post_id,))
    elif not want and exists:
        db.execute(
            "DELETE FROM like_record WHERE user_id=%s AND target_type=2 AND target_id=%s",
            (user["id"], post_id))
        db.execute(
            "UPDATE post SET like_count = GREATEST(like_count - 1, 0) WHERE id=%s", (post_id,))
    p = db.query_one("SELECT like_count FROM post WHERE id=%s", (post_id,))
    return errors.ok({"active": want, "count": p["like_count"]})


@router.post("/posts/{post_id}/favorite")
def toggle_favorite(post_id: int, body: ToggleIn | None = None,
                    user: dict = Depends(current_user)):
    _toggle_target(post_id)
    want = True if body is None or body.liked is None else body.liked
    exists = db.query_one(
        "SELECT 1 AS x FROM favorite WHERE user_id=%s AND post_id=%s",
        (user["id"], post_id))
    if want and not exists:
        db.execute(
            "INSERT INTO favorite (user_id, post_id, created_at) VALUES (%s,%s,%s)",
            (user["id"], post_id, datetime.now()))
        db.execute(
            "UPDATE post SET favorite_count = favorite_count + 1 WHERE id=%s", (post_id,))
    elif not want and exists:
        db.execute("DELETE FROM favorite WHERE user_id=%s AND post_id=%s",
                   (user["id"], post_id))
        db.execute(
            "UPDATE post SET favorite_count = GREATEST(favorite_count - 1, 0) WHERE id=%s",
            (post_id,))
    p = db.query_one("SELECT favorite_count FROM post WHERE id=%s", (post_id,))
    return errors.ok({"active": want, "count": p["favorite_count"]})


# ------------------------------------------------------------------ AI 结果
@router.get("/posts/{post_id}/ai-result")
def ai_result(post_id: int, user: dict = Depends(current_user)):
    from .ai import get_result

    return errors.ok(get_result(post_id))

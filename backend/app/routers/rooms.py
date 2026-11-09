"""聊天室与消息：A-06 ~ A-11。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from .. import db, errors
from ..deps import current_user

router = APIRouter(prefix="/api/v1/rooms", tags=["聊天室"])


# ------------------------------------------------------------------ 入参
class RoomIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    intro: str = ""
    tagIds: list[int] = []


class MessageIn(BaseModel):
    msgType: int = 1
    # 文本 2000 字上限；图片消息存的是 URL，长度另算
    content: str = Field(min_length=1)


class MemberPatch(BaseModel):
    role: int | None = None
    muted: int | None = None
    mutedMinutes: int | None = None


# ------------------------------------------------------------------ 工具
def _room_or_404(room_id: int) -> dict:
    room = db.query_one("SELECT * FROM chat_room WHERE id=%s", (room_id,))
    if not room:
        raise errors.ApiError(errors.CODE_NOT_FOUND, "聊天室不存在")
    return room


def _member(room_id: int, user_id: int) -> dict | None:
    return db.query_one(
        "SELECT * FROM chat_room_member WHERE room_id=%s AND user_id=%s",
        (room_id, user_id),
    )


def _require_member(room_id: int, user_id: int) -> dict:
    m = _member(room_id, user_id)
    if not m:
        raise errors.ApiError(errors.CODE_FORBIDDEN, "请先加入该聊天室")
    return m


def _tag_names(room_ids: list[int]) -> dict[int, list[str]]:
    if not room_ids:
        return {}
    placeholders = ",".join(["%s"] * len(room_ids))
    rows = db.query_all(
        f"SELECT rt.room_id, t.name FROM chat_room_tag rt "
        f"JOIN tag t ON t.id = rt.tag_id WHERE rt.room_id IN ({placeholders})",
        tuple(room_ids),
    )
    result: dict[int, list[str]] = {}
    for r in rows:
        result.setdefault(r["room_id"], []).append(r["name"])
    return result


def _room_vo(r: dict, tags: dict[int, list[str]]) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "intro": r["intro"],
        "creatorId": r["creator_id"],
        "memberCount": r["member_count"],
        "status": r["status"],
        "lastActiveAt": r.get("last_active_at"),
        "createdAt": r.get("created_at"),
        "tags": tags.get(r["id"], []),
    }


# ------------------------------------------------------------------ 房间
@router.get("")
def list_rooms(
    tagId: int | None = None,
    page: int = 1,
    size: int = 20,
    user: dict = Depends(current_user),
):
    sql = "SELECT * FROM chat_room WHERE status = 0"
    args: list = []
    if tagId is not None:
        sql += " AND id IN (SELECT room_id FROM chat_room_tag WHERE tag_id=%s)"
        args.append(tagId)
    sql += " ORDER BY last_active_at DESC, id DESC LIMIT %s OFFSET %s"
    args.extend([max(1, min(size, 50)), (max(1, page) - 1) * max(1, min(size, 50))])
    rooms = db.query_all(sql, tuple(args))
    tags = _tag_names([r["id"] for r in rooms])
    return errors.ok([_room_vo(r, tags) for r in rooms])


@router.post("")
def create_room(body: RoomIn, user: dict = Depends(current_user)):
    now = datetime.now()
    room_id = db.execute(
        "INSERT INTO chat_room (name, intro, creator_id, member_count, status, "
        "last_active_at, created_at) VALUES (%s,%s,%s,1,0,%s,%s)",
        (body.name, body.intro, user["id"], now, now),
    )
    db.execute(
        "INSERT INTO chat_room_member (room_id, user_id, role, muted, joined_at) "
        "VALUES (%s,%s,2,0,%s)",
        (room_id, user["id"], now),
    )
    for tag_id in body.tagIds:
        if db.query_one("SELECT id FROM tag WHERE id=%s", (tag_id,)):
            db.execute(
                "INSERT INTO chat_room_tag (room_id, tag_id, created_at) VALUES (%s,%s,%s)",
                (room_id, tag_id, now),
            )
    room = _room_or_404(room_id)
    return errors.ok(_room_vo(room, _tag_names([room_id])))


@router.get("/{room_id}")
def room_detail(room_id: int, user: dict = Depends(current_user)):
    room = _room_or_404(room_id)
    return errors.ok(_room_vo(room, _tag_names([room_id])))


@router.post("/{room_id}/join")
def join_room(room_id: int, user: dict = Depends(current_user)):
    room = _room_or_404(room_id)
    if room["status"] == 2:
        raise errors.ApiError(errors.CODE_FORBIDDEN, "聊天室已关闭")
    if _member(room_id, user["id"]):
        raise errors.ApiError(errors.CODE_CONFLICT, "已加入该聊天室")
    db.execute(
        "INSERT INTO chat_room_member (room_id, user_id, role, muted, joined_at) "
        "VALUES (%s,%s,0,0,%s)",
        (room_id, user["id"], datetime.now()),
    )
    db.execute(
        "UPDATE chat_room SET member_count = member_count + 1 WHERE id=%s", (room_id,)
    )
    return errors.ok()


@router.get("/{room_id}/members")
def room_members(room_id: int, user: dict = Depends(current_user)):
    _room_or_404(room_id)
    _require_member(room_id, user["id"])
    rows = db.query_all(
        "SELECT m.*, u.nickname FROM chat_room_member m "
        "JOIN `user` u ON u.id = m.user_id WHERE m.room_id=%s",
        (room_id,),
    )
    return errors.ok([
        {
            "userId": r["user_id"],
            "nickname": r["nickname"],
            "role": r["role"],
            "muted": r["muted"],
            "mutedUntil": r.get("muted_until"),
            "joinedAt": r.get("joined_at"),
        }
        for r in rows
    ])


@router.patch("/{room_id}/members/{target_id}")
def patch_member(room_id: int, target_id: int, body: MemberPatch,
                 user: dict = Depends(current_user)):
    if body.role is None and body.muted is None:
        raise errors.ApiError(errors.CODE_PARAM, "role 与 muted 至少传一个")
    _room_or_404(room_id)
    me = _require_member(room_id, user["id"])
    if (me["role"] or 0) < 1:
        raise errors.ApiError(errors.CODE_FORBIDDEN, "仅群主或管理员可管理成员")
    target = _member(room_id, target_id)
    if not target:
        raise errors.ApiError(errors.CODE_NOT_FOUND, "该用户不在聊天室中")
    if target["role"] == 2:
        raise errors.ApiError(errors.CODE_FORBIDDEN, "不能修改群主")

    sets, args = [], []
    if body.role is not None:
        sets.append("role=%s")
        args.append(body.role)
    if body.muted is not None:
        sets.append("muted=%s")
        args.append(body.muted)
        until = None
        if body.muted == 1 and body.mutedMinutes:
            from datetime import timedelta

            until = datetime.now() + timedelta(minutes=body.mutedMinutes)
        sets.append("muted_until=%s")
        args.append(until)
    args.extend([room_id, target_id])
    db.execute(
        f"UPDATE chat_room_member SET {', '.join(sets)} WHERE room_id=%s AND user_id=%s",
        tuple(args),
    )
    return errors.ok()


# ------------------------------------------------------------------ 消息
@router.get("/{room_id}/messages")
def list_messages(room_id: int, cursor: int | None = None, limit: int = 20,
                  user: dict = Depends(current_user)):
    _room_or_404(room_id)
    _require_member(room_id, user["id"])
    size = max(1, min(limit, 50))
    sql = ("SELECT m.*, u.nickname FROM message m LEFT JOIN `user` u ON u.id = m.sender_id "
           "WHERE m.room_id=%s AND m.status=0")
    args: list = [room_id]
    if cursor:
        sql += " AND m.id < %s"
        args.append(cursor)
    sql += " ORDER BY m.id DESC LIMIT %s"
    args.append(size + 1)

    rows = db.query_all(sql, tuple(args))
    has_more = len(rows) > size
    rows = rows[:size][::-1]          # 反转为时间正序
    next_cursor = rows[0]["id"] if has_more and rows else None
    return errors.ok({
        "items": [
            {
                "id": r["id"],
                "roomId": r["room_id"],
                "senderId": r["sender_id"],
                "senderNickname": r.get("nickname"),
                "msgType": r["msg_type"],
                "content": r["content"],
                "status": r["status"],
                "createdAt": r.get("created_at"),
            }
            for r in rows
        ],
        "nextCursor": next_cursor,
        "hasMore": has_more,
    })


@router.post("/{room_id}/messages/{msg_id}/recall")
def recall_message(room_id: int, msg_id: int, user: dict = Depends(current_user)):
    """撤回自己的消息：仅限发送者本人、2 分钟内、未撤回。"""
    from datetime import timedelta

    row = db.query_one(
        "SELECT * FROM message WHERE id=%s AND room_id=%s", (msg_id, room_id))
    if not row:
        raise errors.ApiError(errors.CODE_NOT_FOUND, "消息不存在")
    if row["sender_id"] != user["id"]:
        raise errors.ApiError(errors.CODE_FORBIDDEN, "只能撤回自己发的消息")
    if row["status"] != 0:
        raise errors.ApiError(errors.CODE_CONFLICT, "该消息已不可撤回")
    if row["created_at"] + timedelta(minutes=2) < datetime.now():
        raise errors.ApiError(errors.CODE_FORBIDDEN, "超过 2 分钟，无法撤回")
    db.execute("UPDATE message SET status=2 WHERE id=%s", (msg_id,))
    return errors.ok()


@router.post("/{room_id}/messages")
def send_message(room_id: int, body: MessageIn, user: dict = Depends(current_user)):
    room = _room_or_404(room_id)
    if room["status"] == 2:
        raise errors.ApiError(errors.CODE_FORBIDDEN, "聊天室已关闭，无法发言")
    member = _require_member(room_id, user["id"])
    until = member.get("muted_until")
    if member["muted"] == 1 and (until is None or until > datetime.now()):
        raise errors.ApiError(errors.CODE_FORBIDDEN, "你已被禁言")

    if body.msgType == 1 and len(body.content) > 2000:
        raise errors.ApiError(errors.CODE_PARAM, "content 长度不能超过 2000 字")
    if body.msgType in (2, 3) and not body.content.startswith("/uploads/"):
        raise errors.ApiError(errors.CODE_PARAM, "图片/文件消息需先上传，content 应为 /uploads/ 开头的地址")

    now = datetime.now()
    msg_id = db.execute(
        "INSERT INTO message (room_id, sender_id, msg_type, content, status, "
        "ai_processed, created_at) VALUES (%s,%s,%s,%s,0,0,%s)",
        (room_id, user["id"], body.msgType, body.content, now),
    )
    db.execute("UPDATE chat_room SET last_active_at=%s WHERE id=%s", (now, room_id))
    row = db.query_one(
        "SELECT m.*, u.nickname FROM message m LEFT JOIN `user` u ON u.id=m.sender_id "
        "WHERE m.id=%s", (msg_id,),
    )
    return errors.ok({
        "id": row["id"],
        "roomId": row["room_id"],
        "senderId": row["sender_id"],
        "senderNickname": row.get("nickname"),
        "msgType": row["msg_type"],
        "content": row["content"],
        "status": row["status"],
        "createdAt": row.get("created_at"),
    })

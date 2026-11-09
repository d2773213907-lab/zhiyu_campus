"""个人中心：我的资料、我的帖子、我的收藏、我的聊天室。"""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import re

from .. import db, errors
from ..security import hash_password, verify_password
from ..deps import current_user

router = APIRouter(prefix="/api/v1/users/me", tags=["个人中心"])

PASSWORD_RULE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,64}$")

STATUS_TEXT = {0: "正常", 1: "待审", 2: "已删除"}


class PasswordIn(BaseModel):
    oldPassword: str = Field(min_length=1, max_length=64)
    newPassword: str = Field(min_length=8, max_length=64)


class ProfileIn(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=32)
    avatarUrl: str | None = Field(default=None, max_length=255)


def _user_vo(u: dict) -> dict:
    return {
        "id": u["id"],
        "account": u["account"],
        "nickname": u["nickname"],
        "avatarUrl": u.get("avatar_url"),
        "role": u["role"],
        "points": u["points"],
        "status": u["status"],
        "createdAt": u.get("created_at"),
    }


@router.put("")
def update_profile(body: ProfileIn, user: dict = Depends(current_user)):
    """修改昵称或头像。只允许改自己的资料。"""
    sets, args = [], []
    if body.nickname is not None:
        sets.append("nickname=%s")
        args.append(body.nickname)
    if body.avatarUrl is not None:
        sets.append("avatar_url=%s")
        args.append(body.avatarUrl)
    if not sets:
        raise errors.ApiError(errors.CODE_PARAM, "昵称和头像至少传一个")

    args.append(user["id"])
    db.execute(f"UPDATE `user` SET {', '.join(sets)} WHERE id=%s", tuple(args))
    row = db.query_one("SELECT * FROM `user` WHERE id=%s", (user["id"],))
    return errors.ok(_user_vo(row))


@router.post("/password")
def change_password(body: PasswordIn, user: dict = Depends(current_user)):
    """修改自己的口令：校验原口令 + 强度 + 不能与旧的相同。"""
    row = db.query_one("SELECT * FROM `user` WHERE id=%s", (user["id"],))
    if not row:
        raise errors.ApiError(errors.CODE_NOT_FOUND, "用户不存在")
    if not verify_password(body.oldPassword, row["password_hash"]):
        raise errors.ApiError(errors.CODE_UNAUTHORIZED, "原口令不正确")
    if not PASSWORD_RULE.match(body.newPassword):
        raise errors.ApiError(errors.CODE_PARAM, "新口令需 8~64 位且同时包含字母与数字")
    if body.oldPassword == body.newPassword:
        raise errors.ApiError(errors.CODE_PARAM, "新口令不能与原口令相同")
    db.execute("UPDATE `user` SET password_hash=%s WHERE id=%s",
               (hash_password(body.newPassword), user["id"]))
    return errors.ok()


@router.get("/posts")
def my_posts(page: int = 1, size: int = 20, user: dict = Depends(current_user)):
    """我发过的帖子，包含待审和已删除的（自己能看到）。"""
    limit = max(1, min(size, 50))
    rows = db.query_all(
        "SELECT p.*, b.name AS board_name FROM post p "
        "LEFT JOIN board b ON b.id = p.board_id "
        "WHERE p.author_id=%s ORDER BY p.id DESC LIMIT %s OFFSET %s",
        (user["id"], limit, (max(1, page) - 1) * limit))
    return errors.ok([
        {
            "id": r["id"],
            "title": r["title"],
            "excerpt": (r["body"] or "")[:60],
            "boardName": r.get("board_name"),
            "status": r["status"],
            "statusText": STATUS_TEXT.get(r["status"], "未知"),
            "viewCount": r["view_count"],
            "likeCount": r["like_count"],
            "favoriteCount": r["favorite_count"],
            "createdAt": r.get("created_at"),
        }
        for r in rows
    ])


@router.get("/favorites")
def my_favorites(page: int = 1, size: int = 20, user: dict = Depends(current_user)):
    limit = max(1, min(size, 50))
    rows = db.query_all(
        "SELECT p.*, f.created_at AS fav_at, b.name AS board_name FROM favorite f "
        "JOIN post p ON p.id = f.post_id "
        "LEFT JOIN board b ON b.id = p.board_id "
        "WHERE f.user_id=%s ORDER BY f.created_at DESC LIMIT %s OFFSET %s",
        (user["id"], limit, (max(1, page) - 1) * limit))
    return errors.ok([
        {
            "id": r["id"],
            "title": r["title"],
            "excerpt": (r["body"] or "")[:60],
            "boardName": r.get("board_name"),
            "likeCount": r["like_count"],
            "favoritedAt": r.get("fav_at"),
        }
        for r in rows
    ])


@router.get("/rooms")
def my_rooms(user: dict = Depends(current_user)):
    rows = db.query_all(
        "SELECT r.*, m.role AS my_role, m.muted AS my_muted, m.joined_at "
        "FROM chat_room_member m JOIN chat_room r ON r.id = m.room_id "
        "WHERE m.user_id=%s ORDER BY m.joined_at DESC", (user["id"],))
    return errors.ok([
        {
            "id": r["id"],
            "name": r["name"],
            "intro": r["intro"],
            "memberCount": r["member_count"],
            "myRole": r["my_role"],
            "myMuted": r["my_muted"],
            "joinedAt": r.get("joined_at"),
        }
        for r in rows
    ])


@router.get("/stats")
def my_stats(user: dict = Depends(current_user)):
    """个人页顶部的几个数字。"""
    stats = db.query_one(
        "SELECT "
        " (SELECT COUNT(*) FROM post WHERE author_id=%s) AS posts,"
        " (SELECT COUNT(*) FROM favorite WHERE user_id=%s) AS favorites,"
        " (SELECT COUNT(*) FROM chat_room_member WHERE user_id=%s) AS rooms,"
        " (SELECT COUNT(*) FROM like_record WHERE user_id=%s) AS likes,"
        " (SELECT COUNT(*) FROM reply WHERE author_id=%s) AS replies",
        (user["id"], user["id"], user["id"], user["id"], user["id"]))
    return errors.ok(stats)

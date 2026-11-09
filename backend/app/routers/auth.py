"""认证与用户：A-01 ~ A-04。"""

import re
import time

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from .. import config, db, errors
from ..deps import current_user
from ..security import (
    access_seconds,
    hash_password,
    make_access_token,
    make_refresh_token,
    verify_password,
)

router = APIRouter(prefix="/api/v1", tags=["认证与用户"])

PASSWORD_RULE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,64}$")

# 登录失败计数：{账号: [失败次数, 首次失败时间]}，进程内即可
_failures: dict[str, list] = {}


def _is_locked(account: str) -> bool:
    item = _failures.get(account)
    if not item:
        return False
    count, first_at, until = item
    if until and time.time() < until:
        return True
    if until and time.time() >= until:
        _failures.pop(account, None)
        return False
    # 超过一小时没再失败，重新计数
    if time.time() - first_at > 3600:
        _failures.pop(account, None)
    return False


def _record_failure(account: str) -> None:
    now = time.time()
    item = _failures.get(account)
    if not item or now - item[1] > 3600:
        _failures[account] = [1, now, 0]
        return
    count = item[0] + 1
    until = now + config.LOCK_MINUTES * 60 if count >= config.MAX_LOGIN_FAILURES else 0
    _failures[account] = [count, item[1], until]


class RegisterIn(BaseModel):
    account: str = Field(min_length=4, max_length=32)
    nickname: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=8, max_length=64)


class LoginIn(BaseModel):
    account: str
    password: str


class RefreshIn(BaseModel):
    refreshToken: str


def _user_vo(u: dict) -> dict:
    return {
        "id": u["id"],
        "account": u["account"],
        "nickname": u["nickname"],
        "role": u["role"],
        "points": u["points"],
        "status": u["status"],
        "createdAt": u.get("created_at"),
    }


def _login_vo(u: dict) -> dict:
    return {
        "accessToken": make_access_token(u["id"], u["role"]),
        "refreshToken": make_refresh_token(u["id"]),
        "tokenType": "Bearer",
        "expiresIn": access_seconds(),
        "userId": u["id"],
        "nickname": u["nickname"],
        "role": u["role"],
    }


@router.post("/auth/register")
def register(body: RegisterIn):
    if not PASSWORD_RULE.match(body.password):
        raise errors.ApiError(errors.CODE_PARAM, "口令需 8~64 位且同时包含字母与数字")
    if db.query_one("SELECT id FROM `user` WHERE account=%s", (body.account,)):
        raise errors.ApiError(errors.CODE_CONFLICT, "账号已注册")
    user_id = db.execute(
        "INSERT INTO `user` (account, nickname, password_hash, role, points, status) "
        "VALUES (%s, %s, %s, 0, 0, 0)",
        (body.account, body.nickname, hash_password(body.password)),
    )
    user = db.query_one("SELECT * FROM `user` WHERE id=%s", (user_id,))
    return errors.ok(_user_vo(user))


@router.post("/auth/login")
def login(body: LoginIn):
    if _is_locked(body.account):
        raise errors.ApiError(errors.CODE_RATE_LIMIT, "失败次数过多，请 10 分钟后再试")
    user = db.query_one("SELECT * FROM `user` WHERE account=%s", (body.account,))
    if not user or not verify_password(body.password, user["password_hash"]):
        _record_failure(body.account)
        raise errors.ApiError(errors.CODE_UNAUTHORIZED, "账号或口令错误")
    if user["status"] != 0:
        raise errors.ApiError(errors.CODE_FORBIDDEN, "账号已被禁用")
    _failures.pop(body.account, None)
    return errors.ok(_login_vo(user))


@router.post("/auth/refresh")
def refresh(body: RefreshIn):
    from ..security import decode_token

    try:
        payload = decode_token(body.refreshToken)
    except Exception:
        raise errors.ApiError(errors.CODE_UNAUTHORIZED, "刷新令牌无效或已过期")
    if payload.get("typ") != "refresh":
        raise errors.ApiError(errors.CODE_UNAUTHORIZED, "请使用刷新令牌")
    user = db.query_one("SELECT * FROM `user` WHERE id=%s", (int(payload["sub"]),))
    if not user or user["status"] != 0:
        raise errors.ApiError(errors.CODE_UNAUTHORIZED, "账号不可用")
    return errors.ok(_login_vo(user))


@router.get("/users/me")
def me(user: dict = Depends(current_user)):
    row = db.query_one("SELECT * FROM `user` WHERE id=%s", (user["id"],))
    if not row:
        raise errors.ApiError(errors.CODE_NOT_FOUND, "用户不存在")
    return errors.ok(_user_vo(row))

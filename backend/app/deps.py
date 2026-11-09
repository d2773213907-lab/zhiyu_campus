"""请求依赖：从请求头里解析登录用户。

用法：
    @router.get("/users/me")
    def me(user: dict = Depends(current_user)):
        ...
"""

from fastapi import Header

from . import errors
from .security import decode_token


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise errors.ApiError(errors.CODE_UNAUTHORIZED, "缺少访问令牌")
    token = authorization[7:]
    try:
        payload = decode_token(token)
    except Exception:
        raise errors.ApiError(errors.CODE_UNAUTHORIZED, "令牌无效或已过期")
    if payload.get("typ") != "access":
        raise errors.ApiError(errors.CODE_UNAUTHORIZED, "请使用访问令牌")
    return {"id": int(payload["sub"]), "role": int(payload.get("role", 0))}


def require_admin(user: dict) -> None:
    if user.get("role") != 2:
        raise errors.ApiError(errors.CODE_FORBIDDEN, "仅管理员可访问审核台")

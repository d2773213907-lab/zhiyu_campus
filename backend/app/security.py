"""口令哈希与 JWT 令牌。

和 Java 版保持同一份令牌格式（HS256，claims: sub/role/typ/iat/exp），
所以前端和旧令牌都不用改。
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from . import config


# ------------------------------------------------------------------ 口令
def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # 种子数据里可能有占位符，直接当作不匹配
        return False


# -------------------------------------------------------------------- JWT
def _make_token(user_id: int, role: int, typ: str, expires: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "typ": typ,
        "iat": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def make_access_token(user_id: int, role: int) -> str:
    return _make_token(user_id, role, "access", timedelta(minutes=config.ACCESS_MINUTES))


def make_refresh_token(user_id: int) -> str:
    return _make_token(user_id, 0, "refresh", timedelta(days=config.REFRESH_DAYS))


def decode_token(token: str) -> dict:
    """解析失败会抛 jwt.PyJWTError，由调用方处理。"""
    return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])


def access_seconds() -> int:
    return config.ACCESS_MINUTES * 60

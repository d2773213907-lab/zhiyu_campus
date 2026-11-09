"""统一响应与异常。

所有接口都返回同一个结构：{code, message, data, traceId}
和 Java 版完全一致，前端不用改。
"""

import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

# 与报告表 23 一致的错误码
CODE_OK = 0
CODE_PARAM = 40001
CODE_UNAUTHORIZED = 40101
CODE_FORBIDDEN = 40301
CODE_NOT_FOUND = 40401
CODE_CONFLICT = 40901
CODE_RATE_LIMIT = 42901
CODE_INTERNAL = 50001
CODE_DEPENDENCY = 50301

_STATUS = {
    CODE_PARAM: 400,
    CODE_UNAUTHORIZED: 401,
    CODE_FORBIDDEN: 403,
    CODE_NOT_FOUND: 404,
    CODE_CONFLICT: 409,
    CODE_RATE_LIMIT: 429,
    CODE_INTERNAL: 500,
    CODE_DEPENDENCY: 503,
}


class ApiError(Exception):
    """业务异常：带错误码，由全局处理器转成统一响应。"""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = _STATUS.get(code, 400)


def trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", "-")


def ok(data=None) -> dict:
    return {"code": CODE_OK, "message": "success", "data": data}


def fail(request: Request, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=_STATUS.get(code, 400),
        content={
            "code": code,
            "message": message,
            "data": None,
            "traceId": trace_id(request),
        },
    )


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]

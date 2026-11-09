"""应用入口。

启动：  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
或者：  python run.py
"""

import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import errors
from .routers import admin, agent, auth, files, me, posts, rooms, search

app = FastAPI(title="知屿校园 API（Python 版）", version="1.0.0")

app.add_middleware(GZipMiddleware, minimum_size=800)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    """开发期禁用静态资源缓存，避免改了页面浏览器还在用旧的。"""
    response = await call_next(request)
    path = request.url.path.lower()
    if path.startswith("/vendor/"):
        # 第三方库几乎不变，让浏览器长期缓存，第二次打开就不用再下 1MB
        response.headers["Cache-Control"] = "public, max-age=604800"
    elif path.endswith((".html", ".js", ".css")) or path == "/":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


@app.middleware("http")
async def add_trace_id(request: Request, call_next):
    """给每个请求生成 traceId，方便按一次调用串日志。"""
    request.state.trace_id = errors.new_trace_id()
    response = await call_next(request)
    response.headers["X-Trace-Id"] = request.state.trace_id
    return response


@app.exception_handler(errors.ApiError)
async def handle_api_error(request: Request, exc: errors.ApiError):
    return errors.fail(request, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def handle_validation(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(x) for x in first.get("loc", [])[1:]) or "参数"
    msg = first.get("msg", "格式不正确")
    return errors.fail(request, errors.CODE_PARAM, f"{field} {msg}")


@app.exception_handler(StarletteHTTPException)
async def handle_http(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return errors.fail(request, errors.CODE_NOT_FOUND, "接口不存在")
    return errors.fail(request, errors.CODE_INTERNAL, str(exc.detail))


@app.exception_handler(Exception)
async def handle_other(request: Request, exc: Exception):
    import traceback

    traceback.print_exc()
    return errors.fail(request, errors.CODE_INTERNAL, "服务内部错误，请联系管理员")


# ------------------------------------------------------------------ 路由
app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(posts.router)
app.include_router(search.router)
app.include_router(admin.router)
app.include_router(agent.router)
app.include_router(files.router)
app.include_router(me.router)



# 未实现的 /api 路径统一返回 40401（否则会被静态文件挂载吞掉）
@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def api_not_found(path: str):
    raise errors.ApiError(errors.CODE_NOT_FOUND, "接口不存在")
# 上传的图片
_UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
os.makedirs(_UPLOAD_DIR, exist_ok=True)


@app.get("/uploads/{name}")
def serve_upload(name: str, download: int = 0):
    """图片默认内嵌显示，加 ?download=1 变为下载；其他文件一律下载。"""
    safe = os.path.basename(name)
    path = os.path.join(_UPLOAD_DIR, safe)
    if not os.path.isfile(path):
        raise errors.ApiError(errors.CODE_NOT_FOUND, "文件不存在")
    image = safe.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
    if image and not download:
        return FileResponse(path)
    return FileResponse(path, filename=safe, content_disposition_type="attachment")

# ------------------------------------------------------------ 前端静态文件
# 复用 Java 版那套前端，路径不用改
_STATIC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..",
                 "software", "campus", "src", "main", "resources", "static")
)
if os.path.isdir(_STATIC):
    app.mount("/", StaticFiles(directory=_STATIC, html=True), name="static")

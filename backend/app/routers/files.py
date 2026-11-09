"""文件上传：聊天室发图片和文档用。

两类：
  - 图片：jpg/png/gif/webp，≤ 5 MB
  - 文档：pdf/doc/docx/xls/xlsx/ppt/pptx/txt/zip/rar/7z，≤ 20 MB
存本地 uploads 目录，文件名带原始名字，方便前端显示。
真实项目应换成对象存储（MinIO/OSS），接口形状不用变。
"""

import os
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, UploadFile

from .. import errors
from ..deps import current_user

router = APIRouter(prefix="/api/v1/files", tags=["文件"])

UPLOAD_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
FILE_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
             ".txt", ".zip", ".rar", ".7z"}

IMAGE_MAX = 5 * 1024 * 1024        # 5 MB
FILE_MAX = 20 * 1024 * 1024        # 20 MB


def _safe_name(name: str) -> str:
    """只保留中英文、数字、点、下划线、短横线，避免路径穿越。"""
    name = os.path.basename(name or "file")
    name = re.sub(r"[^\w\u4e00-\u9fa5.\-]", "_", name)
    return name[:60] or "file"


@router.post("")
async def upload(file: UploadFile = File(...), user: dict = Depends(current_user)):
    ctype = (file.content_type or "").lower()
    original = _safe_name(file.filename or "")
    ext = os.path.splitext(original)[1].lower()

    is_image = ctype in IMAGE_TYPES
    if is_image:
        ext = IMAGE_TYPES[ctype]
        limit, kind = IMAGE_MAX, "image"
    elif ext in FILE_EXTS:
        limit, kind = FILE_MAX, "file"
    else:
        raise errors.ApiError(
            errors.CODE_PARAM,
            "支持图片（jpg/png/gif/webp）与文档（pdf/word/excel/ppt/txt/zip 等）")

    data = await file.read()
    if not data:
        raise errors.ApiError(errors.CODE_PARAM, "文件为空")
    if len(data) > limit:
        mb = limit // (1024 * 1024)
        raise errors.ApiError(errors.CODE_PARAM, f"文件不能超过 {mb} MB")

    stored = f"{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:8]}-{original}"
    if not stored.lower().endswith(ext):
        stored += ext
    with open(os.path.join(UPLOAD_DIR, stored), "wb") as fh:
        fh.write(data)

    return errors.ok({
        "url": f"/uploads/{stored}",
        "name": original,
        "size": len(data),
        "kind": kind,
    })
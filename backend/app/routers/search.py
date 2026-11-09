"""统一检索 + 行为采集 + 管理接口。

检索实现报告 8.3.1 的公式：
    score = 0.5×相关度 + 0.3×热度 + 0.2×偏好
三个分项各自归一化到 [0,1]，所以 score 也在 [0,1]。
"""

import math
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import config, db, errors
from ..deps import current_user, require_admin

router = APIRouter(prefix="/api/v1", tags=["检索与行为"])


# ------------------------------------------------------------------ 检索
def _occurrences(text: str | None, kw: str) -> int:
    if not text or not kw:
        return 0
    return text.count(kw)


def _decay(when: datetime | None) -> float:
    if not when:
        return 1.0
    days = (datetime.now() - when).total_seconds() / 86400
    return math.exp(-config.RECENCY_LAMBDA * max(days, 0))


def _preference(user_id: int) -> dict[int, float]:
    """从行为日志统计用户对各标签的兴趣权重。"""
    logs = db.query_all(
        "SELECT * FROM behavior_log WHERE user_id=%s ORDER BY id DESC LIMIT 500",
        (user_id,))
    if not logs:
        return {}
    post_ids = [l["target_id"] for l in logs if l["target_type"] == 3]
    if not post_ids:
        return {}
    marks = ",".join(["%s"] * len(post_ids))
    links = db.query_all(
        f"SELECT post_id, tag_id FROM post_tag WHERE post_id IN ({marks})",
        tuple(post_ids))
    by_post: dict[int, list[int]] = {}
    for l in links:
        by_post.setdefault(l["post_id"], []).append(l["tag_id"])

    weights = {1: 1.0, 2: 2.0, 3: 5.0, 4: 3.0, 5: 4.0}
    result: dict[int, float] = {}
    for log in logs:
        if log["target_type"] != 3:
            continue
        w = weights.get(log["action"], 0.0)
        if log["action"] == 6:
            w = (log.get("stay_ms") or 0) / 10000.0
        for tag_id in by_post.get(log["target_id"], []):
            result[tag_id] = result.get(tag_id, 0.0) + w
    return result


@router.get("/search")
def search(q: str = "", tagId: int | None = None, limit: int | None = None,
           user: dict = Depends(current_user)):
    q = (q or "").strip()
    size = max(1, min(limit or config.DEFAULT_LIMIT, 50))

    # ---- 召回：帖子 + 聊天室
    posts_sql = "SELECT * FROM post WHERE status=0"
    posts_args: list = []
    if q:
        posts_sql += " AND (title LIKE %s OR body LIKE %s)"
        posts_args.extend([f"%{q}%", f"%{q}%"])
    if tagId is not None:
        posts_sql += " AND id IN (SELECT post_id FROM post_tag WHERE tag_id=%s)"
        posts_args.append(tagId)
    posts_sql += f" ORDER BY id DESC LIMIT {config.RECALL_LIMIT}"
    posts = db.query_all(posts_sql, tuple(posts_args))

    rooms_sql = "SELECT * FROM chat_room WHERE status=0"
    rooms_args: list = []
    if q:
        rooms_sql += " AND (name LIKE %s OR intro LIKE %s)"
        rooms_args.extend([f"%{q}%", f"%{q}%"])
    if tagId is not None:
        rooms_sql += " AND id IN (SELECT room_id FROM chat_room_tag WHERE tag_id=%s)"
        rooms_args.append(tagId)
    rooms_sql += f" ORDER BY id DESC LIMIT {config.RECALL_LIMIT}"
    rooms = db.query_all(rooms_sql, tuple(rooms_args))

    if not posts and not rooms:
        return errors.ok([])

    tag_names = {t["id"]: t["name"] for t in db.query_all("SELECT id, name FROM tag")}
    post_tag_map: dict[int, list[int]] = {}
    if posts:
        marks = ",".join(["%s"] * len(posts))
        for r in db.query_all(
                f"SELECT post_id, tag_id FROM post_tag WHERE post_id IN ({marks})",
                tuple(p["id"] for p in posts)):
            post_tag_map.setdefault(r["post_id"], []).append(r["tag_id"])
    room_tag_map: dict[int, list[int]] = {}
    if rooms:
        marks = ",".join(["%s"] * len(rooms))
        for r in db.query_all(
                f"SELECT room_id, tag_id FROM chat_room_tag WHERE room_id IN ({marks})",
                tuple(x["id"] for x in rooms)):
            room_tag_map.setdefault(r["room_id"], []).append(r["tag_id"])

    pref_by_tag = _preference(user["id"])

    rows = []
    for p in posts:
        tags = post_tag_map.get(p["id"], [])
        # 相关度：标题命中算 2 倍
        rel = 2 * _occurrences(p["title"], q) + _occurrences(p["body"], q) if q else 0.5
        heat_raw = (p["view_count"] + 3 * p["like_count"] + 4 * p["favorite_count"]) \
            * _decay(p.get("created_at"))
        pref = sum(pref_by_tag.get(t, 0.0) for t in tags) / len(tags) if tags else 0.0
        rows.append({"type": "post", "id": p["id"], "title": p["title"],
                     "excerpt": (p["body"] or "")[:60], "rel": rel, "heat": heat_raw,
                     "pref": pref, "tags": [tag_names.get(t, "") for t in tags]})

    for r in rooms:
        tags = room_tag_map.get(r["id"], [])
        rel = 2 * _occurrences(r["name"], q) + _occurrences(r["intro"], q) if q else 0.5
        heat_raw = 5.0 * (r["member_count"] or 0) * _decay(r.get("last_active_at"))
        pref = sum(pref_by_tag.get(t, 0.0) for t in tags) / len(tags) if tags else 0.0
        rows.append({"type": "room", "id": r["id"], "title": r["name"],
                     "excerpt": (r["intro"] or "")[:60], "rel": rel, "heat": heat_raw,
                     "pref": pref, "tags": [tag_names.get(t, "") for t in tags]})

    # ---- 归一化
    for key in ("rel", "heat", "pref"):
        top = max((x[key] for x in rows), default=0)
        for x in rows:
            x[key] = x[key] / top if top > 0 else 0.0

    for x in rows:
        x["score"] = round(
            config.REL_WEIGHT * x["rel"]
            + config.HEAT_WEIGHT * x["heat"]
            + config.PREF_WEIGHT * x["pref"], 4)
        x["rel"] = round(x["rel"], 4)
        x["heat"] = round(x["heat"], 4)
        x["pref"] = round(x["pref"], 4)

    rows.sort(key=lambda x: x["score"], reverse=True)
    return errors.ok(rows[:size])


# ------------------------------------------------------------------ 行为
class BehaviorIn(BaseModel):
    action: int
    targetType: int
    targetId: int
    stayMs: int = 0


@router.post("/behaviors", status_code=202)
def report_behavior(body: BehaviorIn, user: dict = Depends(current_user)):
    if not 1 <= body.action <= 6:
        raise errors.ApiError(errors.CODE_PARAM, "action 取值需为 1~6")
    if not 1 <= body.targetType <= 5:
        raise errors.ApiError(errors.CODE_PARAM, "targetType 取值需为 1~5")
    db.execute(
        "INSERT INTO behavior_log (user_id, action, target_type, target_id, stay_ms, "
        "created_at) VALUES (%s,%s,%s,%s,%s,%s)",
        (user["id"], body.action, body.targetType, body.targetId, body.stayMs,
         datetime.now()))
    return errors.ok()


# ------------------------------------------------------------------ 热度
@router.post("/admin/heat/recalc")
def recalc_heat(user: dict = Depends(current_user)):
    require_admin(user)
    posts = db.query_all("SELECT * FROM post WHERE status=0")
    heat_by_post = {
        p["id"]: (p["view_count"] + 3 * p["like_count"] + 4 * p["favorite_count"])
        * _decay(p.get("created_at"))
        for p in posts
    }
    tag_heat: dict[int, float] = {}
    if heat_by_post:
        marks = ",".join(["%s"] * len(heat_by_post))
        for r in db.query_all(
                f"SELECT post_id, tag_id FROM post_tag WHERE post_id IN ({marks})",
                tuple(heat_by_post.keys())):
            tag_heat[r["tag_id"]] = tag_heat.get(r["tag_id"], 0.0) \
                + heat_by_post.get(r["post_id"], 0.0)
    for t in db.query_all("SELECT id FROM tag"):
        db.execute("UPDATE tag SET heat=%s WHERE id=%s",
                   (int(round(tag_heat.get(t["id"], 0.0))), t["id"]))
    return errors.ok({"tags": len(tag_heat)})

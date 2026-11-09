"""AI 处理：摘要、情感、自动打标、违规判定。对应报告 UC-10 与 8.3.3。

本文件是"模型替身"：用确定性规则模拟大模型输出，离线也能演示。
接真实模型时只需要改 _call_model 一个函数（见 agent.py 里的实现方式）。
"""

from datetime import datetime

from .. import db, errors, llm

TAG_KEYWORDS = {
    "考研": "考研", "高数": "考研", "选课": "选课", "期末": "选课",
    "实习": "实习", "社团": "社团", "二手": "二手", "求助": "求助",
}
POSITIVE = ["谢谢", "感谢", "不错", "赞", "有用", "分享"]
NEGATIVE = ["垃圾", "骗", "坑", "差评", "投诉"]
HARD = ["代写", "代考", "赌博", "毒品", "枪", "色情", "诈骗"]
SOFT = ["收费", "私聊报价", "包过", "内部渠道"]



MODEL_PROMPT = (
    "你是校园社区的内容审核助手。读下面这篇帖子，输出一行 JSON，字段：\n"
    "summary   一句话摘要，不超过 60 字\n"
    "sentiment 情感：1 正面 / 0 中性 / -1 负面\n"
    "violation 是否可能违规：true / false\n"
    "confidence 违规置信度，0~1 的小数\n"
    "tags      从这些标签中选 0~3 个：考研、选课、实习、社团、二手、求助\n"
    "只输出 JSON，不要解释。"
)


def _analyze(title: str, body: str) -> dict:
    """优先用模型；没密钥或调用失败时退回本地规则。"""
    text = (title or "") + (body or "")

    if llm.available():
        out = llm.chat_json(MODEL_PROMPT, f"标题：{title}\n正文：{body}")
        if out:
            try:
                return {
                    "summary": str(out.get("summary", ""))[:120],
                    "sentiment": int(out.get("sentiment", 0)),
                    "violation": bool(out.get("violation", False)),
                    "confidence": float(out.get("confidence", 0.0)),
                    "tags": [t for t in (out.get("tags") or []) if t in TAG_KEYWORDS.values()],
                }
            except Exception as exc:
                print(f"[ai] 模型结果解析失败，用规则：{exc}")
    summary = (body or "").strip()
    if len(summary) > 60:
        summary = summary[:60] + "…"

    sentiment = 0
    if any(w in text for w in POSITIVE):
        sentiment = 1
    elif any(w in text for w in NEGATIVE):
        sentiment = -1

    violation, confidence = False, 0.05
    if any(w in text for w in HARD):
        violation, confidence = True, 0.92
    elif any(w in text for w in SOFT):
        violation, confidence = True, 0.65

    tags = []
    for kw, name in TAG_KEYWORDS.items():
        if kw in text and name not in tags:
            tags.append(name)

    return {"summary": summary, "sentiment": sentiment,
            "violation": violation, "confidence": confidence, "tags": tags}


def analyze_post(post_id: int) -> dict:
    """对帖子做一次处理并落库。重复调用会覆盖旧结果。"""
    post = db.query_one("SELECT * FROM post WHERE id=%s", (post_id,))
    if not post:
        raise errors.ApiError(errors.CODE_NOT_FOUND, "帖子不存在")

    out = _analyze(post["title"], post["body"])
    now = datetime.now()

    old = db.query_one("SELECT * FROM ai_result WHERE post_id=%s", (post_id,))
    if old:
        result_id = old["id"]
        db.execute(
            "UPDATE ai_result SET summary=%s, sentiment=%s, violation=%s, "
            "confidence=%s, processed_at=%s WHERE id=%s",
            (out["summary"], out["sentiment"], 1 if out["violation"] else 0,
             out["confidence"], now, result_id))
        db.execute("DELETE FROM ai_result_tag WHERE result_id=%s", (result_id,))
    else:
        result_id = db.execute(
            "INSERT INTO ai_result (post_id, summary, sentiment, violation, "
            "confidence, processed_at) VALUES (%s,%s,%s,%s,%s,%s)",
            (post_id, out["summary"], out["sentiment"], 1 if out["violation"] else 0,
             out["confidence"], now))

    for name in out["tags"]:
        tag = db.query_one("SELECT id FROM tag WHERE name=%s", (name,))
        if tag:
            db.execute(
                "INSERT INTO ai_result_tag (result_id, tag_id, confidence, source) "
                "VALUES (%s,%s,0.8,1)", (result_id, tag["id"]))

    # 违规只决定是否进入待审，绝不自动删除（NFR-08）
    if out["violation"] and out["confidence"] >= 0.5 and post["status"] == 0:
        db.execute("UPDATE post SET status=1 WHERE id=%s", (post_id,))
        print(f"[AI] 帖子 {post_id} 判定违规（{out['confidence']}），已置为待审")

    return get_result(post_id)


def get_result(post_id: int) -> dict:
    row = db.query_one("SELECT * FROM ai_result WHERE post_id=%s", (post_id,))
    if not row:
        raise errors.ApiError(errors.CODE_NOT_FOUND, "该内容尚未被 AI 处理")
    tags = db.query_all(
        "SELECT t.id, t.name, at2.confidence FROM ai_result_tag at2 "
        "JOIN tag t ON t.id = at2.tag_id WHERE at2.result_id=%s", (row["id"],))
    return {
        "id": row["id"],
        "postId": row["post_id"],
        "summary": row["summary"],
        "sentiment": row["sentiment"],
        "violation": bool(row["violation"]),
        "confidence": float(row["confidence"]),
        "tags": [{"tagId": t["id"], "name": t["name"],
                  "confidence": float(t["confidence"])} for t in tags],
        "processedAt": row.get("processed_at"),
    }

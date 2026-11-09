"""AI 智能体：总 agent + 三个子 agent。

两种模式：
  1) 配了模型密钥（AI_ENABLED=true + AI_API_KEY）——真模型：
     模型判断意图 → 子 agent 查数据 → 模型根据数据写回答
  2) 没配密钥——本地规则：
     关键词判断意图 → 子 agent 查数据 → 固定话术回答
模式 2 是为了断网/没密钥时功能不瘫，但它不是 AI。
"""

import json
import urllib.request
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import config, db, errors, llm
from ..deps import current_user
from .search import search as search_api

router = APIRouter(prefix="/api/v1/agent", tags=["AI 智能体"])

ROUTE_PROMPT = (
    "你是校园社区平台的路由器。判断用户这句话属于哪一类，只输出一个词。\n"
    "chat      —— 和聊天室有关：查房间、加入房间、发消息、看聊天记录\n"
    "post      —— 和帖子有关：浏览帖子、发帖、回帖\n"
    "search    —— 想查找某些内容、按关键词检索\n"
    "chitchat  —— 打招呼、问你是谁、问能做什么、与平台数据无关的闲聊\n"
    "只输出这一个词，不要标点、不要解释。"
)

ANSWER_PROMPT = (
    "你是「知屿校园」的 AI 助手。下面给出系统刚查到的真实数据（JSON）。\n"
    "请用简洁、自然的中文回答用户的问题，只能依据这些数据，不要编造。\n"
    "如果数据为空，就如实说没有找到。回答控制在 120 字以内。"
)

CHAT_PROMPT = (
    "你是「知屿校园」的 AI 助手，一个校园社区平台里的助手。\n"
    "平台有聊天室、博客帖子、统一检索、AI 内容审核、个人中心。\n"
    "请用简洁自然的中文回答，控制在 80 字以内。"
)

LOCAL_INTRO = (
    "我是知屿校园的助手，可以帮你：\n"
    "· 查有哪些聊天室、进房间发言\n"
    "· 看最新帖子、发帖、回帖\n"
    "· 按关键词搜索内容\n"
    "目前运行在「本地规则」模式（没配模型密钥），所以回答是固定话术。"
)


class AgentContext(BaseModel):
    """前端传来的"我现在在哪"，让 AI 知道用户当前所处的页面。"""
    page: str | None = None        # chat / post / search ...
    roomId: int | None = None      # 当前聊天室
    postId: int | None = None      # 当前帖子


class AgentIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    context: AgentContext | None = None


# ------------------------------------------------------------------ 模型
def _route(text: str) -> tuple[str, str]:
    """返回 (域, 来源说明)。"""
    if llm.available():
        out = llm.chat(ROUTE_PROMPT, text, temperature=0.1)
        if out:
            word = out.strip().strip("。.，,").lower()
            for word_ok in ("chat", "post", "search", "chitchat"):
                if word_ok in word:
                    return word_ok, "llm"
    return _rule_route(text), "rules"


def _rule_route(text: str) -> str:
    if any(k in text for k in ("你好", "你是谁", "能做什么", "帮助", "怎么用", "介绍一下")):
        return "chitchat"
    if any(k in text for k in ("聊天室", "房间", "群聊", "消息", "发言", "禁言", "自习室")):
        return "chat"
    if "说" in text or "发消息" in text:
        return "chat"
    if any(k in text for k in ("帖子", "发帖", "回帖", "博客", "楼主")):
        return "post"
    return "search"


# ------------------------------------------------------------------ 子 agent
def _summarize_room(user: dict, room_id: int, text: str) -> dict | None:
    """用当前房间的最近消息回答问题。"""
    room = db.query_one("SELECT * FROM chat_room WHERE id=%s", (room_id,))
    if not room:
        return None
    rows = db.query_all(
        "SELECT m.content, u.nickname FROM message m LEFT JOIN `user` u ON u.id=m.sender_id "
        "WHERE m.room_id=%s AND m.status=0 ORDER BY m.id DESC LIMIT 20", (room_id,))
    rows = rows[::-1]
    if not rows:
        return {"action": "summarizeRoom",
                "reply": f"「{room['name']}」里还没有消息。",
                "data": {"roomId": room_id, "count": 0}}
    transcript = "\n".join(f"{r['nickname']}: {r['content']}" for r in rows)

    if llm.available():
        answer = llm.chat(
            "你在总结一个校园聊天室最近的对话。用 3~5 句中文概括大家在聊什么、"
            "有没有需要跟进的事。不要编造，只依据给出的聊天记录。",
            f"聊天室名称：{room['name']}\n最近消息：\n{transcript}")
        if answer:
            return {"action": "summarizeRoom", "reply": answer,
                    "data": {"roomId": room_id, "count": len(rows)},
                    "answered": True}

    tail = "；".join(f"{r['nickname']}：{r['content']}" for r in rows[-5:])
    return {"action": "summarizeRoom",
            "reply": f"「{room['name']}」最近 {len(rows)} 条消息：{tail}。",
            "data": {"roomId": room_id, "count": len(rows)}}


def _chat_agent(user: dict, text: str, ctx=None) -> dict:
    # 有上下文房间 + 问"总结/聊了什么" —— 直接看这个房间
    if ctx and ctx.roomId and any(k in text for k in
                                  ("总结", "聊了什么", "在聊什么", "最近消息", "说了什么", "记录")):
        got = _summarize_room(user, ctx.roomId, text)
        if got:
            return got

    if "在" in text and ("说" in text or "发" in text):
        head = text.split("在", 1)[1]
        for sep in ("说", "发消息", "发"):
            if sep in head:
                room_name, content = head.split(sep, 1)
                content = content.lstrip("：: ").strip()
                room = db.query_one(
                    "SELECT * FROM chat_room WHERE name LIKE %s LIMIT 1",
                    (f"%{room_name.strip()}%",))
                if room and content:
                    now = datetime.now()
                    db.execute(
                        "INSERT INTO message (room_id, sender_id, msg_type, content, "
                        "status, ai_processed, created_at) VALUES (%s,%s,1,%s,0,0,%s)",
                        (room["id"], user["id"], content, now))
                    db.execute("UPDATE chat_room SET last_active_at=%s WHERE id=%s",
                               (now, room["id"]))
                    return {"action": "sendMessage",
                            "reply": f"已在「{room['name']}」发出：{content}",
                            "data": {"roomId": room["id"], "content": content}}

    if "加入" in text or "进入" in text:
        name = text.replace("加入", "").replace("进入", "").strip()
        room = db.query_one("SELECT * FROM chat_room WHERE name LIKE %s LIMIT 1",
                            (f"%{name}%",))
        if room:
            exists = db.query_one(
                "SELECT 1 AS x FROM chat_room_member WHERE room_id=%s AND user_id=%s",
                (room["id"], user["id"]))
            if not exists:
                db.execute(
                    "INSERT INTO chat_room_member (room_id, user_id, role, muted, joined_at) "
                    "VALUES (%s,%s,0,0,%s)", (room["id"], user["id"], datetime.now()))
                db.execute("UPDATE chat_room SET member_count = member_count + 1 "
                           "WHERE id=%s", (room["id"],))
            return {"action": "joinRoom",
                    "reply": f"已加入「{room['name']}」。",
                    "data": {"roomId": room["id"], "roomName": room["name"]}}

    rooms = db.query_all(
        "SELECT * FROM chat_room WHERE status=0 ORDER BY last_active_at DESC LIMIT 5")
    names = "、".join(f"「{r['name']}」({r['member_count']}人)" for r in rooms)
    return {"action": "listRooms",
            "reply": f"当前有 {len(rooms)} 个聊天室：{names}。" if rooms else "还没有聊天室。",
            "data": {"rooms": [{"id": r["id"], "name": r["name"],
                                "memberCount": r["member_count"]} for r in rooms]}}


def _summarize_post(post_id: int) -> dict | None:
    post = db.query_one("SELECT * FROM post WHERE id=%s", (post_id,))
    if not post:
        return None
    replies = db.query_all(
        "SELECT content, author_id FROM reply WHERE post_id=%s AND status=0 "
        "ORDER BY id ASC LIMIT 10", (post_id,))
    reply_text = "\n".join(f"- {r['content']}" for r in replies) or "（暂无回帖）"

    if llm.available():
        answer = llm.chat(
            "你在向用户解释当前这篇校园论坛帖子。用 3~4 句中文说明它讲了什么、"
            "讨论的焦点是什么。只依据给定内容，不要编造。",
            f"标题：{post['title']}\n正文：{post['body']}\n回帖：\n{reply_text}")
        if answer:
            return {"action": "summarizePost", "reply": answer,
                    "data": {"postId": post_id, "title": post["title"]},
                    "answered": True}

    body = (post["body"] or "")[:80]
    return {"action": "summarizePost",
            "reply": f"《{post['title']}》：{body}…（共 {len(replies)} 条回帖）",
            "data": {"postId": post_id, "title": post["title"]}}


def _post_agent(user: dict, text: str, ctx=None) -> dict:
    if ctx and ctx.postId and any(k in text for k in
                                  ("这篇", "总结", "讲了什么", "说的什么", "内容", "评价")):
        got = _summarize_post(ctx.postId)
        if got:
            return got

    if "发帖" in text or "发布" in text:
        content = text.replace("发帖", "").replace("发布", "").strip("：: ")
        title = content[:20] if content else "无标题"
        board = db.query_one("SELECT * FROM board ORDER BY sort_no LIMIT 1")
        now = datetime.now()
        post_id = db.execute(
            "INSERT INTO post (board_id, author_id, title, body, status, view_count, "
            "like_count, favorite_count, created_at) VALUES (%s,%s,%s,%s,0,0,0,0,%s)",
            (board["id"], user["id"], title, content, now))
        return {"action": "createPost",
                "reply": f"已发布到「{board['name']}」：{title}",
                "data": {"postId": post_id, "status": 0}}

    posts = db.query_all(
        "SELECT * FROM post WHERE status=0 ORDER BY created_at DESC LIMIT 5")
    names = "、".join(f"「{p['title']}」" for p in posts)
    return {"action": "listPosts",
            "reply": f"最新 {len(posts)} 篇帖子：{names}。" if posts else "还没有帖子。",
            "data": {"posts": [{"id": p["id"], "title": p["title"],
                                "likeCount": p["like_count"]} for p in posts]}}


def _search_agent(user: dict, text: str) -> dict:
    keyword = text
    for w in ("帮我", "请", "搜索一下", "搜索", "搜一下", "搜", "查找", "找一下", "找",
              "查一下", "查询"):
        keyword = keyword.replace(w, "")
    keyword = keyword.strip() or text.strip()

    items = search_api(q=keyword, tagId=None, limit=5, user=user)["data"]
    if not items:
        return {"action": "search", "reply": f"没有找到和「{keyword}」相关的内容。",
                "data": {"keyword": keyword, "count": 0}}
    names = "、".join(f"《{i['title']}》(score {i['score']})" for i in items)
    return {"action": "search",
            "reply": f"「{keyword}」找到 {len(items)} 条：{names}。",
            "data": {"keyword": keyword, "items": items}}


# ------------------------------------------------------------------ 总入口
@router.post("/chat")
def agent_chat(body: AgentIn, user: dict = Depends(current_user)):
    text = body.message.strip()
    domain, route_src = _route(text)
    trace = [f"router:{route_src}->{domain}",
             "model:" + (llm.model_name())]

    # 闲聊：直接由模型回答；没有密钥就给能力介绍
    if domain == "chitchat":
        answer = llm.chat(CHAT_PROMPT, text) if llm.available() else LOCAL_INTRO
        return errors.ok({"agent": "chitchat", "action": "answer",
                          "reply": answer or LOCAL_INTRO,
                          "data": {}, "trace": trace})

    handler = {"chat": _chat_agent, "post": _post_agent, "search": _search_agent}[domain]
    result = handler(user, text, body.context)

    # 子 agent 已经用模型答过（比如总结），就不要再拿精简数据重新生成一次
    already_answered = result.pop("answered", False)

    # 有模型时，用真实数据让模型重新组织回答（而不是固定话术）
    if (not already_answered) and llm.available() and result.get("data"):
        composed = llm.chat(
            ANSWER_PROMPT,
            f"用户问题：{text}\n\n系统数据：{json.dumps(result['data'], ensure_ascii=False)}")
        if composed:
            result["reply"] = composed
            trace.append("answer:llm")
        else:
            trace.append("answer:template")
    else:
        trace.append("answer:template")

    result["agent"] = domain
    result["trace"] = trace
    return errors.ok(result)


@router.get("/info")
def agent_info(user: dict = Depends(current_user)):
    return errors.ok({
        "llmAvailable": llm.available(),
        "model": llm.model_name(),
        "mode": "llm" if llm.available() else "rules",
        "subAgents": ["chat", "post", "search", "chitchat"],
    })

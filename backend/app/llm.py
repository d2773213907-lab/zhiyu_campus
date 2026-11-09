"""统一的大模型调用封装。

所有需要模型的地方都走这里：
  - agent 路由与回答
  - 发帖后的摘要、情感、打标、违规判定
没有密钥时 available() 返回 False，调用方自行降级。
"""

import json
import urllib.request

from . import config


def available() -> bool:
    return config.AI_ENABLED and bool(config.AI_API_KEY)


def model_name() -> str:
    return config.AI_MODEL if available() else "local-rules"


def chat(system: str, user: str, temperature: float = 0.3) -> str | None:
    """返回模型文本；任何失败都返回 None，由调用方降级。"""
    if not available():
        return None
    body = json.dumps({
        "model": config.AI_MODEL,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{config.AI_BASE_URL}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {config.AI_API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=config.AI_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        print(f"[llm] 调用失败，降级：{exc}")
        return None


def chat_json(system: str, user: str, temperature: float = 0.1) -> dict | None:
    """要求模型返回 JSON；解析失败返回 None。"""
    out = chat(system, user, temperature)
    if not out:
        return None
    text = out.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except Exception:
        print(f"[llm] JSON 解析失败：{text[:120]}")
        return None

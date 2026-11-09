# -*- coding: utf-8 -*-
"""补充测试：TC-33 个人中心、TC-34 图片上传。

输出 extra-results.json，与 run_tests.ps1 的结果合并后写回报告。
"""

import json
import os
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8080"
PROJ = r"C:\Users\saxtul\Documents\ds harness区\01_软件工程课程\知屿校园-建模大作业"
OUT = os.path.join(PROJ, "software", "extra-results.json")


def call(path, data=None, token=None, raw=None, ctype="application/json", method=None):
    headers = {"Content-Type": ctype}
    if token:
        headers["Authorization"] = "Bearer " + token
    if raw is not None:
        body = raw
    elif data is not None:
        body = json.dumps(data).encode()
    else:
        body = None
    req = urllib.request.Request(BASE + path, data=body, headers=headers,
                                 method=method or ("POST" if body is not None else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def js(body):
    try:
        return json.loads(body)
    except Exception:
        return {}


def main():
    results = []

    # 准备一个测试账号
    account = "m" + uuid.uuid4().hex[:10]
    call("/api/v1/auth/register",
         {"account": account, "nickname": "个人中心测试", "password": "abc12345"})
    st, body = call("/api/v1/auth/login", {"account": account, "password": "abc12345"})
    token = js(body)["data"]["accessToken"]

    # ---------------------------------------------------------- TC-33
    st1, b1 = call("/api/v1/users/me/stats", token=token)
    st2, b2 = call("/api/v1/users/me/posts", token=token)
    st3, b3 = call("/api/v1/users/me/favorites", token=token)
    st4, b4 = call("/api/v1/users/me/rooms", token=token)
    st5, b5 = call("/api/v1/users/me", {"nickname": "改过的昵称"}, token=token, method="PUT")
    keys_ok = all(k in js(b1).get("data", {}) for k in ("posts", "favorites", "rooms"))
    ok = (st1 == st2 == st3 == st4 == st5 == 200 and keys_ok
          and js(b5)["data"]["nickname"] == "改过的昵称")
    results.append({
        "id": "TC-33",
        "scene": "个人中心",
        "expected": "资料可改，我的帖子/收藏/聊天室/统计均返回 200",
        "actual": (f"stats={st1}、posts={st2}、favorites={st3}、rooms={st4}、"
                   f"改昵称={st5}，新昵称={js(b5).get('data', {}).get('nickname')}"),
        "verdict": "通过" if ok else "未通过",
        "note": "",
    })

    # ---------------------------------------------------------- TC-34
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d4944415478da63f8cfc0f01f0005fe0201d4a2f6b70000000049454e44ae426082")
    boundary = "----zy" + uuid.uuid4().hex
    payload = b"".join([
        ("--" + boundary + "\r\n").encode(),
        b'Content-Disposition: form-data; name="file"; filename="t.png"\r\n',
        b"Content-Type: image/png\r\n\r\n", png,
        ("\r\n--" + boundary + "--\r\n").encode(),
    ])
    st_u, b_u = call("/api/v1/files", token=token, raw=payload,
                     ctype="multipart/form-data; boundary=" + boundary)
    url = js(b_u).get("data", {}).get("url", "")

    # 图片可访问
    st_img = 0
    if url:
        try:
            with urllib.request.urlopen(BASE + url, timeout=10) as r:
                st_img = r.status
        except Exception:
            st_img = 0

    # 发图片消息
    st_rooms, b_rooms = call("/api/v1/rooms", token=token)
    room_id = js(b_rooms)["data"][0]["id"]
    call(f"/api/v1/rooms/{room_id}/join", {}, token=token)
    st_msg, b_msg = call(f"/api/v1/rooms/{room_id}/messages",
                         {"msgType": 2, "content": url}, token=token)

    # 非本站地址应被拒绝
    st_bad, b_bad = call(f"/api/v1/rooms/{room_id}/messages",
                         {"msgType": 2, "content": "http://evil/x.png"}, token=token)
    ok = (st_u == 200 and st_img == 200 and st_msg == 200
          and st_bad == 400 and js(b_bad).get("code") == 40001)
    results.append({
        "id": "TC-34",
        "scene": "图片上传与发送",
        "expected": "上传 200，图片可访问，图片消息可发送，外链图片被拒 40001",
        "actual": (f"上传={st_u}、访问={st_img}、发图片消息={st_msg}、"
                   f"外链={st_bad}/{js(b_bad).get('code')}"),
        "verdict": "通过" if ok else "未通过",
        "note": "",
    })

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    for r in results:
        print(r["id"], r["verdict"], r["actual"])


if __name__ == "__main__":
    main()

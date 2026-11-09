# -*- coding: utf-8 -*-
"""第 7 轮：把「个人中心」与「图片上传」补进报告，并把技术选型改成 FastAPI。"""

import copy
import os
import sys

from docx import Document
from docx.oxml.ns import qn

BUILD = r"C:\Users\saxtul\Documents\ds harness区\01_软件工程课程\知屿校园-建模大作业\_build"
PROJ = r"C:\Users\saxtul\Documents\ds harness区\01_软件工程课程\知屿校园-建模大作业"
SRC = os.path.join(PROJ, "知屿校园-需求分析与建模实验报告-第6轮修订.docx")
OUT = os.path.join(PROJ, "知屿校园-需求分析与建模实验报告-第7轮修订.docx")

sys.path.insert(0, BUILD)
from build_round1 import set_cell_text  # noqa: E402

UC15 = ["UC-15", "个人中心（资料与我的内容）",
        "查看与修改个人资料、我的帖子、我的收藏、我的聊天室、个人统计",
        "用户", "P1"]

NEW_API = [
    ["A-24", "PUT", "/api/v1/users/me", "修改个人资料（昵称、头像）", "登录"],
    ["A-25", "GET", "/api/v1/users/me/posts", "我的帖子（含待审与已删除）", "登录"],
    ["A-26", "GET", "/api/v1/users/me/favorites", "我的收藏", "登录"],
    ["A-27", "GET", "/api/v1/users/me/rooms", "我的聊天室与我的角色", "登录"],
    ["A-28", "GET", "/api/v1/users/me/stats", "个人统计（帖子/收藏/房间/点赞/回帖）", "登录"],
    ["A-29", "POST", "/api/v1/files", "上传图片，返回可访问地址", "登录"],
]

TECH = ("技术选型（与已实现的工程保持一致，可按团队熟悉程度替换，不改变本节的分层结论）："
        "前端 Vue 3 + Element Plus；后端 Python 3.12 + FastAPI + Pydantic，数据库访问使用 "
        "PyMySQL 直接执行参数化 SQL；数据库 MySQL 8.0；认证采用 JWT（HS256）；"
        "接口文档由 FastAPI 自动生成（/docs）。"
        "选择 Python 而非 Java 框架的原因是团队对该语言更熟悉，"
        "同等功能下代码量约为 Java 实现的三分之一，便于维护与答辩讲解。"
        "大模型通过适配层对接，本期以本地规则实现替代，接口契约不变。")


def add_row(table, values):
    """复制最后一行（保留格式），替换文字。"""
    tr = copy.deepcopy(table.rows[-1]._tr)
    table._tbl.append(tr)
    cells = tr.findall(qn("w:tc"))
    for tc, val in zip(cells, values):
        set_cell_text(tc, val)


def main():
    doc = Document(SRC)

    # 1) 表 3 追加 UC-15
    t_func = doc.tables[2]
    if not any("UC-15" in r.cells[0].text for r in t_func.rows):
        add_row(t_func, UC15)
        print("表 3 已加 UC-15")

    # 2) 表 21 修正 A-05 方法 + 追加 A-24~A-29
    t_api = doc.tables[20]
    for row in t_api.rows:
        if row.cells[0].text.strip() == "A-05":
            row.cells[1].text = "PUT"
            print("A-05 方法改为 PUT")
    existing = {r.cells[0].text.strip() for r in t_api.rows}
    for item in NEW_API:
        if item[0] not in existing:
            add_row(t_api, item)
    print("表 21 现有接口行数:", len(t_api.rows) - 1)

    # 3) 技术选型
    changed = 0
    for p in doc.paragraphs:
        if p.text.strip().startswith("技术选型"):
            if p.runs:
                p.runs[0].text = TECH
                for extra in p.runs[1:]:
                    extra._element.getparent().remove(extra._element)
            else:
                p.add_run(TECH)
            changed += 1
    print("技术选型段落更新:", changed)

    # 4) 正文里的接口数量表述
    fixed = 0
    for p in doc.paragraphs:
        if "23 个接口" in p.text:
            new_text = p.text.replace("23 个接口", "29 个接口")
            for run in p.runs:
                run.text = ""
            if p.runs:
                p.runs[0].text = new_text
            else:
                p.add_run(new_text)
            fixed += 1
    print("接口数量表述更新:", fixed)

    doc.save(OUT)
    print("saved:", OUT)


if __name__ == "__main__":
    main()

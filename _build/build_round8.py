# -*- coding: utf-8 -*-
"""第 8 轮：把 TC-33（个人中心）与 TC-34（图片上传）补进第 9 章，并更新统计。"""

import copy
import json
import os
import sys

from docx import Document
from docx.oxml.ns import qn

BUILD = r"C:\Users\saxtul\Documents\ds harness区\01_软件工程课程\知屿校园-建模大作业\_build"
PROJ = r"C:\Users\saxtul\Documents\ds harness区\01_软件工程课程\知屿校园-建模大作业"
SRC = os.path.join(PROJ, "知屿校园-需求分析与建模实验报告-第7轮修订.docx")
OUT = os.path.join(PROJ, "知屿校园-需求分析与建模实验报告-第8轮修订.docx")
RESULTS = os.path.join(PROJ, "software", "test-results.json")

sys.path.insert(0, BUILD)
from build_round1 import set_cell_text  # noqa: E402

CASE_META = {
    "TC-33": ["TC-33", "A-24~A-28 / UC-15", "个人中心",
              "进入「我的」，改昵称，查看三个标签页",
              "资料可改，我的帖子/收藏/聊天室/统计均返回 200"],
    "TC-34": ["TC-34", "A-29 / UC-03", "上传并发送图片",
              "选一张 png 上传后作为图片消息发送",
              "上传 200、图片可访问、消息可发、外链图片被拒 40001"],
}


def add_row(table, values):
    tr = copy.deepcopy(table.rows[-1]._tr)
    table._tbl.append(tr)
    for tc, val in zip(tr.findall(qn("w:tc")), values):
        set_cell_text(tc, val)


def has_id(table, value):
    return any(r.cells[0].text.strip() == value for r in table.rows)


def main():
    with open(RESULTS, encoding="utf-8-sig") as fh:
        results = {r["id"]: r for r in json.load(fh)}

    doc = Document(SRC)

    # ---- 表 29（7 列）追加两行
    t_cases = doc.tables[28]
    for tid in ("TC-33", "TC-34"):
        if has_id(t_cases, tid):
            continue
        meta = CASE_META[tid]
        r = results.get(tid, {})
        add_row(t_cases, meta + [r.get("actual", "—"), r.get("verdict", "未执行")])
        print("表 29 已加", tid)

    # ---- 表 34 统计
    for tb in doc.tables:
        if tb.rows[0].cells[0].text.strip() != "结果":
            continue
        for row in tb.rows[1:]:
            key = row.cells[0].text.strip()
            if key == "通过":
                row.cells[1].text = "31"
            elif key == "合计":
                row.cells[1].text = "34"
                row.cells[2].text = "功能用例 24 条 + 边界异常用例 10 条"
        print("表 34 已更新")

    # ---- 正文数字
    replacements = [
        ("共 22 条，覆盖本期 12 个用例", "共 24 条，覆盖本期 13 个用例"),
        ("32 条用例的结果统计见表 34", "34 条用例的结果统计见表 34"),
        ("通过率：29/32 = 90.6%", "通过率：31/34 = 91.2%"),
        ("29/30 = 96.7%", "31/32 = 96.9%"),
        ("表 29 的 22 条功能用例全部通过", "表 29 的 24 条功能用例全部通过"),
    ]
    for p in doc.paragraphs:
        text = p.text
        new = text
        for old, rep in replacements:
            if old in new:
                new = new.replace(old, rep)
        if new != text:
            for run in p.runs:
                run.text = ""
            if p.runs:
                p.runs[0].text = new
            else:
                p.add_run(new)
            print("更新段落:", new[:40])

    doc.save(OUT)
    print("saved:", OUT)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""让 AI 助手面板可拖动，并记住位置。"""

import io

PATH = (r"C:\Users\saxtul\Documents\ds harness区\01_软件工程课程\知屿校园-建模大作业"
        r"\software\campus\src\main\resources\static\app.js")

src = io.open(PATH, encoding="utf-8").read()

# ---------------------------------------------------------------- data
old = "      aiMessages: [],"
new = """      aiMessages: [],
      aiPos: null,"""
assert old in src
src = src.replace(old, new, 1)

# ---------------------------------------------------------------- computed
anchor = "  computed: {"
comp = """  computed: {
    aiStyle() {
      if (!this.aiPos) return {};
      return {
        left: this.aiPos.x + 'px',
        top: this.aiPos.y + 'px',
        right: 'auto',
        bottom: 'auto'
      };
    },"""
assert anchor in src
src = src.replace(anchor, comp, 1)

# ---------------------------------------------------------------- methods
m_anchor = "    async askAI() {"
methods = """    startDrag(e) {
      const box = this.$refs.aiBox;
      if (!box) return;
      const rect = box.getBoundingClientRect();
      const offsetX = e.clientX - rect.left;
      const offsetY = e.clientY - rect.top;

      const move = (ev) => {
        const x = Math.min(Math.max(0, ev.clientX - offsetX), window.innerWidth - 120);
        const y = Math.min(Math.max(0, ev.clientY - offsetY), window.innerHeight - 80);
        this.aiPos = { x: x, y: y };
      };
      const up = () => {
        document.removeEventListener('mousemove', move);
        document.removeEventListener('mouseup', up);
        if (this.aiPos) {
          localStorage.setItem('zy_ai_pos', JSON.stringify(this.aiPos));
        }
      };
      document.addEventListener('mousemove', move);
      document.addEventListener('mouseup', up);
      e.preventDefault();
    },
    resetAIPos() {
      this.aiPos = null;
      localStorage.removeItem('zy_ai_pos');
    },
    async askAI() {"""
assert m_anchor in src
src = src.replace(m_anchor, methods, 1)

# ---------------------------------------------------------------- 恢复位置
mounted_anchor = "  mounted() {"
mounted_new = """  mounted() {
    try {
      const saved = localStorage.getItem('zy_ai_pos');
      if (saved) this.aiPos = JSON.parse(saved);
    } catch (e) { /* 忽略损坏的位置数据 */ }"""
assert mounted_anchor in src
src = src.replace(mounted_anchor, mounted_new, 1)

# ---------------------------------------------------------------- 模板
old_box = '  <div class="ai-box" v-if="aiOpen">'
new_box = '  <div class="ai-box" v-if="aiOpen" ref="aiBox" :style="aiStyle">'
assert old_box in src
src = src.replace(old_box, new_box, 1)

old_head = """    <div class="ai-head">
      <span>AI 助手</span>
      <span class="ai-sub">自动判断交给聊天室 / 帖子 / 检索</span>
    </div>"""
new_head = """    <div class="ai-head" @mousedown="startDrag">
      <div class="ai-head-row">
        <span>AI 助手</span>
        <span class="ai-drag-hint">按住拖动 · <a @click.stop="resetAIPos" href="#">复位</a></span>
      </div>
      <span class="ai-sub">自动判断交给聊天室 / 帖子 / 检索</span>
    </div>"""
assert old_head in src
src = src.replace(old_head, new_head, 1)

src = src.replace('<span class="ver">v13</span>', '<span class="ver">v14</span>')
io.open(PATH, "w", encoding="utf-8", newline="\n").write(src)

for k, v in {
    "data aiPos": "aiPos: null" in src,
    "computed": "aiStyle()" in src,
    "drag": "startDrag(e)" in src,
    "reset": "resetAIPos()" in src,
    "template": 'ref="aiBox"' in src,
    "version": "v14" in src,
}.items():
    print(("OK  " if v else "MISS ") + k)

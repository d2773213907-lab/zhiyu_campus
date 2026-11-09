# -*- coding: utf-8 -*-
"""让小圆球也能拖动；拖动后点击展开时，面板出现在圆球旁边。"""

import io

PATH = (r"C:\Users\saxtul\Documents\ds harness区\01_软件工程课程\知屿校园-建模大作业"
        r"\software\campus\src\main\resources\static\app.js")

src = io.open(PATH, encoding="utf-8").read()

# ---------------------------------------------------------------- data
old = "      aiPos: null,"
new = """      aiPos: null,
      fabPos: null,"""
assert old in src
src = src.replace(old, new, 1)

# ---------------------------------------------------------------- computed
old_c = """    aiStyle() {"""
new_c = """    fabStyle() {
      if (!this.fabPos) return {};
      return {
        left: this.fabPos.x + 'px',
        top: this.fabPos.y + 'px',
        right: 'auto',
        bottom: 'auto'
      };
    },
    aiStyle() {"""
assert old_c in src
src = src.replace(old_c, new_c, 1)

# ---------------------------------------------------------------- 方法
anchor = "    startDrag(e) {"
methods = """    startFabDrag(e) {
      const startX = e.clientX;
      const startY = e.clientY;
      const rect = e.currentTarget.getBoundingClientRect();
      const offX = startX - rect.left;
      const offY = startY - rect.top;
      let moved = false;

      const move = (ev) => {
        if (!moved && Math.abs(ev.clientX - startX) + Math.abs(ev.clientY - startY) < 4) {
          return;                       // 小于 4px 当作点击，不算拖动
        }
        moved = true;
        const size = 48;
        const x = Math.min(Math.max(0, ev.clientX - offX), window.innerWidth - size);
        const y = Math.min(Math.max(0, ev.clientY - offY), window.innerHeight - size);
        this.fabPos = { x: x, y: y };
      };
      const up = () => {
        document.removeEventListener('mousemove', move);
        document.removeEventListener('mouseup', up);
        if (moved) {
          localStorage.setItem('zy_ai_fab', JSON.stringify(this.fabPos));
        } else {
          this.toggleAI();              // 没拖动就是点击
        }
      };
      document.addEventListener('mousemove', move);
      document.addEventListener('mouseup', up);
      e.preventDefault();
    },
    toggleAI() {
      this.aiOpen = !this.aiOpen;
      // 圆球被拖到别处时，面板贴着它展开
      if (this.aiOpen && !this.aiPos && this.fabPos) {
        this.aiPos = {
          x: Math.max(8, Math.min(this.fabPos.x - 312, window.innerWidth - 368)),
          y: Math.max(8, this.fabPos.y - 470)
        };
      }
    },
    startDrag(e) {"""
assert anchor in src
src = src.replace(anchor, methods, 1)

# ---------------------------------------------------------------- mounted 恢复
old_m = """      const saved = localStorage.getItem('zy_ai_pos');
      if (saved) this.aiPos = JSON.parse(saved);"""
new_m = """      const saved = localStorage.getItem('zy_ai_pos');
      if (saved) this.aiPos = JSON.parse(saved);
      const savedFab = localStorage.getItem('zy_ai_fab');
      if (savedFab) this.fabPos = JSON.parse(savedFab);"""
assert old_m in src
src = src.replace(old_m, new_m, 1)

# ---------------------------------------------------------------- 模板：圆球
old_fab = """  <div class="ai-fab" @click="aiOpen = !aiOpen" :title="aiOpen ? '收起' : '打开 AI 助手'">
    {{ aiOpen ? '×' : 'AI' }}
  </div>"""
new_fab = """  <div class="ai-fab" :style="fabStyle" @mousedown="startFabDrag"
       :title="aiOpen ? '收起' : '打开 AI 助手（可拖动）'">
    {{ aiOpen ? '×' : 'AI' }}
  </div>"""
assert old_fab in src
src = src.replace(old_fab, new_fab, 1)

src = src.replace('<span class="ver">v14</span>', '<span class="ver">v15</span>')
io.open(PATH, "w", encoding="utf-8", newline="\n").write(src)

for k, v in {
    "fabPos": "fabPos: null" in src,
    "fabStyle": "fabStyle()" in src,
    "startFabDrag": "startFabDrag(e)" in src,
    "toggleAI": "toggleAI()" in src,
    "模板": ':style="fabStyle"' in src,
    "version": "v15" in src,
}.items():
    print(("OK  " if v else "MISS ") + k)

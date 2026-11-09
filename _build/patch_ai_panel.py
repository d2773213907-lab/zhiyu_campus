# -*- coding: utf-8 -*-
"""给前端加 AI 助手悬浮面板。"""

import io

PATH = (r"C:\Users\saxtul\Documents\ds harness区\01_软件工程课程\知屿校园-建模大作业"
        r"\software\campus\src\main\resources\static\app.js")

src = io.open(PATH, encoding="utf-8").read()

# ---------------------------------------------------------------- 1) data
old_data = "      pending: null,"
new_data = """      pending: null,
      aiOpen: false,
      aiInput: '',
      aiLoading: false,
      aiMessages: [],"""
assert old_data in src
src = src.replace(old_data, new_data, 1)

# ---------------------------------------------------------------- 2) 方法
anchor = "    async loadMe() {"
methods = """    async askAI() {
      const text = this.aiInput.trim();
      if (!text || this.aiLoading) return;
      this.aiMessages.push({ role: 'user', text: text });
      this.aiInput = '';
      this.aiLoading = true;
      try {
        const res = await api('/agent/chat', { method: 'POST', body: { message: text } });
        this.aiMessages.push({
          role: 'ai',
          text: res.reply,
          agent: res.agent,
          trace: (res.trace || []).join(' | ')
        });
      } catch (e) {
        this.aiMessages.push({ role: 'ai', text: '出错了：' + e.message, agent: 'error' });
      } finally {
        this.aiLoading = false;
        this.$nextTick(() => {
          const box = this.$refs.aiList;
          if (box) box.scrollTop = box.scrollHeight;
        });
      }
    },
    async loadMe() {"""
assert anchor in src
src = src.replace(anchor, methods, 1)

# ---------------------------------------------------------------- 3) 模板
panel = """
  <!-- AI 助手 -->
  <div class="ai-fab" @click="aiOpen = !aiOpen" :title="aiOpen ? '收起' : '打开 AI 助手'">
    {{ aiOpen ? '×' : 'AI' }}
  </div>

  <div class="ai-box" v-if="aiOpen">
    <div class="ai-head">
      <span>AI 助手</span>
      <span class="ai-sub">自动判断交给聊天室 / 帖子 / 检索</span>
    </div>
    <div class="ai-list" ref="aiList">
      <div v-if="aiMessages.length === 0" class="ai-empty">
        试试问我：<br>
        · 有哪些聊天室<br>
        · 看看最新帖子<br>
        · 帮我搜一下高数
      </div>
      <div v-for="(m, i) in aiMessages" :key="i" :class="['ai-msg', m.role]">
        <div class="ai-bubble">{{ m.text }}</div>
        <div class="ai-meta" v-if="m.agent">
          <el-tag size="small"
                  :type="m.agent === 'chat' ? 'success' : (m.agent === 'post' ? 'warning' : 'info')">
            {{ m.agent }}
          </el-tag>
          <span class="ai-trace">{{ m.trace }}</span>
        </div>
      </div>
      <div v-if="aiLoading" class="ai-msg ai">
        <div class="ai-bubble">思考中…</div>
      </div>
    </div>
    <div class="ai-input">
      <el-input v-model="aiInput" placeholder="说一句话，Enter 发送"
                @keyup.enter="askAI" size="small" />
      <el-button type="primary" size="small" :loading="aiLoading" @click="askAI">发送</el-button>
    </div>
  </div>
"""

tick = chr(96)                      # 模板字符串的结束反引号
marker = tick + "\n};"
end = src.rindex(marker)
pos = src.rindex("</div>", 0, end)  # 根 div 的闭合标签
src = src[:pos] + panel + src[pos:]

src = src.replace('<span class="ver">v12</span>', '<span class="ver">v13</span>')

io.open(PATH, "w", encoding="utf-8", newline="\n").write(src)

checks = {
    "data": "aiOpen: false" in src,
    "method": "async askAI()" in src,
    "panel": 'class="ai-box"' in src,
    "version": "v13" in src,
}
for k, v in checks.items():
    print(("OK  " if v else "MISS ") + k)

/* 知屿校园 · 前端（Vue 3 + Element Plus，无需构建，随 jar 一起发布） */
const { createApp, reactive } = Vue;

const API = '/api/v1';
const TOKEN_KEY = 'zy_token';
const USER_KEY = 'zy_user';

const state = reactive({
  token: localStorage.getItem(TOKEN_KEY) || '',
  user: JSON.parse(localStorage.getItem(USER_KEY) || 'null')
});

async function api(path, options) {
  const opt = options || {};
  const headers = { 'Content-Type': 'application/json' };
  if (state.token) headers.Authorization = 'Bearer ' + state.token;
  let res;
  try {
    res = await fetch(API + path, {
      method: opt.method || 'GET',
      headers,
      body: opt.body ? JSON.stringify(opt.body) : undefined
    });
  } catch (e) {
    // 浏览器原生只会说 "Failed to fetch"，这里翻译成用户能懂的提示
    const err = new Error('连不上后端服务。请确认：1) 后端已启动；2) 你访问的是 http://127.0.0.1:8080 而不是直接打开 html 文件');
    err.status = 0;
    throw err;
  }
  let json = null;
  try { json = await res.json(); } catch (e) { json = null; }
  if (!res.ok || (json && json.code !== 0)) {
    const err = new Error((json && json.message) || ('请求失败：HTTP ' + res.status));
    err.status = res.status;
    err.code = json && json.code;   // 业务错误码，用于区分 40901 等场景
    if (res.status === 401) {
      state.token = '';
      state.user = null;
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      // 关键：令牌失效必须回到登录页，否则页面空白且没有任何提示
      if (location.hash !== '#/login') location.hash = '#/login';
    }
    throw err;
  }
  return json ? json.data : null;
}

function parseHash() {
  const raw = (location.hash || '#/posts').replace(/^#/, '');
  const parts = raw.split('/').filter(Boolean);
  if (parts.length === 0) return { name: 'posts' };
  if (parts[0] === 'rooms' && parts[1]) return { name: 'chat', roomId: Number(parts[1]) };
  if (parts[0] === 'posts' && parts[1]) return { name: 'post', postId: Number(parts[1]) };
  return { name: parts[0] };
}

const app = {
  data() {
    return {
      state,
      route: parseHash(),
      loading: false,
      tab: 'login',
      loginForm: { account: '', password: '', nickname: '' },

      tags: [],
      boards: [],

      rooms: [],
      roomDialog: false,
      roomForm: { name: '', intro: '', tagIds: [] },

      currentRoom: null,
      messages: [],
      msgText: '',
      uploading: false,
      pending: null,
      uiAi: true,           // AI 界面开关
      aiOpen: false,
      aiInput: '',
      aiLoading: false,
      aiMessages: [],
      aiPos: null,
      fabPos: null,
      msgCursor: null,
      timer: null,

      posts: [],
      postDialog: false,
      postForm: { boardId: null, title: '', body: '', tagIds: [] },
      filter: { boardId: null, tagId: null, sort: 'latest' },

      currentPost: null,
      replies: [],
      replyText: '',
      aiResult: null,

      searchQ: '',
      searchResults: [],

      pending: [],
      meTab: 'posts',
      meStats: { posts: 0, favorites: 0, rooms: 0, likes: 0, replies: 0 },
      myPosts: [],
      myFavorites: [],
      myRooms: [],
      editDialog: false,
      profileNickname: '',
      pwdOld: '',
      pwdNew: '',
      pwdConfirm: '',
      reviewRemark: {}
    };
  },
  computed: {
    fabStyle() {
      if (!this.fabPos) return {};
      return {
        left: this.fabPos.x + 'px',
        top: this.fabPos.y + 'px',
        right: 'auto',
        bottom: 'auto'
      };
    },
    aiStyle() {
      if (!this.aiPos) return {};
      return {
        left: this.aiPos.x + 'px',
        top: this.aiPos.y + 'px',
        right: 'auto',
        bottom: 'auto'
      };
    },
    isAdmin() {
      return this.state.user && this.state.user.role === 2;
    },
    loggedIn() {
      return !!this.state.token;
    }
  },
  mounted() {
    try {
      const saved = localStorage.getItem('zy_ai_pos');
      if (saved) this.aiPos = JSON.parse(saved);
      const savedFab = localStorage.getItem('zy_ai_fab');
      if (savedFab) this.fabPos = JSON.parse(savedFab);
    } catch (e) { /* 忽略损坏的位置数据 */ }
    window.addEventListener('hashchange', this.syncRoute);
    if (!this.loggedIn) {
      location.hash = '#/login';
    } else {
      this.bootstrap();
    }
    this.syncRoute();
  },
  beforeUnmount() {
    this.stopPolling();
  },
  methods: {
    /* ---------------------------------------------------------- 基础 */
    go(path) {
      location.hash = '#' + path;
    },
    syncRoute() {
      this.route = parseHash();
      if (!this.loggedIn && this.route.name !== 'login') {
        this.route = { name: 'login' };
        return;
      }
      this.stopPolling();
      const name = this.route.name;
      if (name === 'rooms') this.loadRooms();
      if (name === 'chat') this.openRoom(this.route.roomId);
      if (name === 'posts') this.loadPosts();
      if (name === 'post') this.openPost(this.route.postId);
      if (name === 'search') this.doSearch();
      if (name === 'review') this.loadPending();
      if (name === 'me') this.loadMe();
    },
    async bootstrap() {
      try {
        const [tags, boards] = await Promise.all([
          api('/tags'), api('/boards')
        ]);
        this.tags = tags || [];
        this.boards = boards || [];
      } catch (e) {
        ElementPlus.ElMessage.error(e.message);
      }
    },
    notify(msg, type) {
      ElementPlus.ElMessage({ message: msg, type: type || 'success' });
    },
    fail(e) {
      ElementPlus.ElMessage.error(e.message || '操作失败');
    },

    /* ---------------------------------------------------------- 登录 */
    async doLogin() {
      try {
        const data = await api('/auth/login', {
          method: 'POST',
          body: { account: this.loginForm.account, password: this.loginForm.password }
        });
        this.applyAuth(data);
        this.notify('登录成功');
        this.go('/posts');
      } catch (e) { this.fail(e); }
    },
    async doRegister() {
      try {
        await api('/auth/register', {
          method: 'POST',
          body: {
            account: this.loginForm.account,
            nickname: this.loginForm.nickname,
            password: this.loginForm.password
          }
        });
        this.notify('注册成功，请登录');
        this.tab = 'login';
      } catch (e) { this.fail(e); }
    },
    applyAuth(data) {
      state.token = data.accessToken;
      state.user = { id: data.userId, nickname: data.nickname, role: data.role };
      localStorage.setItem(TOKEN_KEY, state.token);
      localStorage.setItem(USER_KEY, JSON.stringify(state.user));
      this.bootstrap();
    },
    logout() {
      this.stopPolling();
      state.token = '';
      state.user = null;
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      this.go('/login');
    },

    /* -------------------------------------------------------- 聊天室 */
    async loadRooms() {
      try {
        const query = this.filter.tagId ? '?tagId=' + this.filter.tagId : '';
        this.rooms = await api('/rooms' + query);
      } catch (e) { this.fail(e); }
    },
    async createRoom() {
      try {
        await api('/rooms', { method: 'POST', body: this.roomForm });
        this.roomDialog = false;
        this.roomForm = { name: '', intro: '', tagIds: [] };
        this.notify('创建成功');
        this.loadRooms();
      } catch (e) { this.fail(e); }
    },
    async joinRoom(room) {
      try {
        await api('/rooms/' + room.id + '/join', { method: 'POST' });
        this.notify('已加入「' + room.name + '」');
      } catch (e) {
        // 40901 表示已经加入过，直接进房间
        if (e.code !== 40901) { this.fail(e); return; }
      }
      // 双保险：既改 hash（地址栏可分享），也直接切换视图状态
      location.hash = '#/rooms/' + room.id;
      this.route = { name: 'chat', roomId: room.id };
      this.openRoom(room.id);
    },
    async openRoom(roomId) {
      try {
        this.currentRoom = await api('/rooms/' + roomId);
        await this.loadMessages();
        this.startPolling(roomId);
      } catch (e) {
        this.fail(e);
        if (e.status === 403) this.go('/rooms');
      }
    },
    async loadMessages(older) {
      try {
        const query = '?limit=20' + (older && this.msgCursor ? '&cursor=' + this.msgCursor : '');
        const page = await api('/rooms/' + this.currentRoom.id + '/messages' + query);
        if (older) {
          this.messages = (page.items || []).concat(this.messages);
        } else {
          this.messages = page.items || [];
        }
        this.msgCursor = page.nextCursor;
      } catch (e) { this.fail(e); }
    },

    startPolling(roomId) {
      this.stopPolling();
      this.timer = setInterval(async () => {
        if (this.route.name !== 'chat') return;
        try {
          const page = await api('/rooms/' + roomId + '/messages?limit=20');
          this.messages = page.items || [];
        } catch (e) { /* 轮询失败静默处理 */ }
      }, 8000);
    },
    stopPolling() {
      if (this.timer) { clearInterval(this.timer); this.timer = null; }
    },
    pickFile(kind) {
      if (kind === 'image') this.$refs.fileInput.click();
      else this.$refs.docInput.click();
    },
    onFileChosen(ev, kind) {
      const file = ev.target.files && ev.target.files[0];
      if (!file) return;
      // 关键：只暂存，不发送。点“发送”才真正上传
      this.pending = { file, kind, name: file.name, size: file.size };
      ev.target.value = '';
    },
    cancelPending() {
      this.pending = null;
      this.notify('已取消', 'info');
    },
    async sendMessage() {
      // 先处理待发送的附件
      if (this.pending) {
        await this.sendPending();
        return;
      }
      if (!this.msgText.trim()) return;
      try {
        await api('/rooms/' + this.currentRoom.id + '/messages', {
          method: 'POST',
          body: { content: this.msgText, msgType: 1 }
        });
        this.msgText = '';
        await this.loadMessages();
      } catch (e) { this.fail(e); }
    },
    async sendPending() {
      const p = this.pending;
      this.uploading = true;
      try {
        const form = new FormData();
        form.append('file', p.file);
        const res = await fetch('/api/v1/files', {
          method: 'POST',
          headers: { Authorization: 'Bearer ' + state.token },
          body: form
        });
        const json = await res.json();
        if (!res.ok || json.code !== 0) throw new Error(json.message || '上传失败');
        await api('/rooms/' + this.currentRoom.id + '/messages', {
          method: 'POST',
          body: { msgType: p.kind === 'image' ? 2 : 3, content: json.data.url }
        });
        this.pending = null;
        await this.loadMessages();
        this.notify(p.kind === 'image' ? '图片已发送' : '文件已发送');
      } catch (err) {
        this.fail(err);
      } finally {
        this.uploading = false;
      }
    },
    async recall(m) {
      try {
        await api('/rooms/' + this.currentRoom.id + '/messages/' + m.id + '/recall',
                  { method: 'POST' });
        this.notify('已撤回');
        await this.loadMessages();
      } catch (e) { this.fail(e); }
    },
    fileName(url) {
      if (!url) return '文件';
      const base = String(url).split('/').pop();
      // 存盘名形如 20261108-ab12cd34-原文件名.pdf，去掉前缀日期与随机串
      const m = base.match(/^\d{8}-[0-9a-f]+-(.*)$/);
      return m ? decodeURIComponent(m[1]) : decodeURIComponent(base);
    },
    formatTime(value) {
      if (!value) return '';
      const d = new Date(value);
      if (isNaN(d.getTime())) return '';
      const pad = n => (n < 10 ? '0' + n : '' + n);
      return pad(d.getHours()) + ':' + pad(d.getMinutes());
    },

    /* ---------------------------------------------------------- 博客 */
    async loadPosts() {
      try {
        const params = new URLSearchParams();
        if (this.filter.boardId) params.set('boardId', this.filter.boardId);
        if (this.filter.tagId) params.set('tagId', this.filter.tagId);
        params.set('sort', this.filter.sort || 'latest');
        this.posts = await api('/posts?' + params.toString());
      } catch (e) { this.fail(e); }
    },
    async createPost() {
      try {
        const post = await api('/posts', { method: 'POST', body: this.postForm });
        this.postDialog = false;
        this.postForm = { boardId: null, title: '', body: '', tagIds: [] };
        this.notify('发布成功' + (post.status === 1 ? '，内容进入待审' : ''));
        this.loadPosts();
      } catch (e) { this.fail(e); }
    },
    async openPost(postId) {
      try {
        this.currentPost = await api('/posts/' + postId);
        this.replies = await api('/posts/' + postId + '/replies');
        try {
          this.aiResult = await api('/posts/' + postId + '/ai-result');
        } catch (e) { this.aiResult = null; }
      } catch (e) { this.fail(e); }
    },
    async addReply() {
      if (!this.replyText.trim()) return;
      try {
        await api('/posts/' + this.currentPost.id + '/replies', {
          method: 'POST', body: { content: this.replyText }
        });
        this.replyText = '';
        this.notify('回帖成功');
        this.replies = await api('/posts/' + this.currentPost.id + '/replies');
      } catch (e) { this.fail(e); }
    },
    async toggleLike() {
      try {
        const res = await api('/posts/' + this.currentPost.id + '/like', {
          method: 'POST', body: { liked: !this.currentPost.liked }
        });
        this.currentPost.liked = res.active;
        this.currentPost.likeCount = res.count;
      } catch (e) { this.fail(e); }
    },
    async toggleFavorite() {
      try {
        const res = await api('/posts/' + this.currentPost.id + '/favorite', {
          method: 'POST', body: { liked: !this.currentPost.favorited }
        });
        this.currentPost.favorited = res.active;
        this.currentPost.favoriteCount = res.count;
      } catch (e) { this.fail(e); }
    },

    /* ---------------------------------------------------------- 检索 */
    async doSearch() {
      try {
        const params = new URLSearchParams();
        if (this.searchQ) params.set('q', this.searchQ);
        if (this.filter.tagId) params.set('tagId', this.filter.tagId);
        this.searchResults = await api('/search?' + params.toString());
      } catch (e) { this.fail(e); }
    },
    openSearchResult(item) {
      if (item.type === 'post') this.go('/posts/' + item.id);
      else this.go('/rooms/' + item.id);
    },

    /* ---------------------------------------------------------- 审核 */
    startFabDrag(e) {
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
    startDrag(e) {
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
    aiContext() {
      const ctx = {};
      if (this.route.name === 'chat' && this.currentRoom) {
        ctx.page = 'chat';
        ctx.roomId = this.currentRoom.id;
      } else if (this.route.name === 'post' && this.currentPost) {
        ctx.page = 'post';
        ctx.postId = this.currentPost.id;
      } else {
        ctx.page = this.route.name || 'unknown';
      }
      return ctx;
    },
    aiContextText() {
      if (this.route.name === 'chat' && this.currentRoom) {
        return '当前聊天室：' + this.currentRoom.name;
      }
      if (this.route.name === 'post' && this.currentPost) {
        return '当前帖子：' + this.currentPost.title;
      }
      return '当前页面：' + (this.route.name || '');
    },
    async askAI() {
      const text = this.aiInput.trim();
      if (!text || this.aiLoading) return;
      this.aiMessages.push({ role: 'user', text: text });
      this.aiInput = '';
      this.aiLoading = true;
      try {
        const ctx = this.aiContext();
        const res = await api('/agent/chat', {
          method: 'POST',
          body: { message: text, context: ctx }
        });
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
    async loadMe() {
      try {
        const [stats, posts, favs, rooms] = await Promise.all([
          api('/users/me/stats'),
          api('/users/me/posts'),
          api('/users/me/favorites'),
          api('/users/me/rooms')
        ]);
        this.meStats = stats || this.meStats;
        this.myPosts = posts || [];
        this.myFavorites = favs || [];
        this.myRooms = rooms || [];
        this.profileNickname = state.user.nickname;
      } catch (e) { this.fail(e); }
    },
    async saveProfile() {
      try {
        // 1) 改密码（填了才处理）
        if (this.pwdNew || this.pwdOld) {
          if (!this.pwdOld || !this.pwdNew) throw new Error('改密码需要同时填原口令和新口令');
          if (this.pwdNew !== this.pwdConfirm) throw new Error('两次输入的新口令不一致');
          await api('/users/me/password', {
            method: 'POST',
            body: { oldPassword: this.pwdOld, newPassword: this.pwdNew }
          });
          this.pwdOld = ''; this.pwdNew = ''; this.pwdConfirm = '';
        }
        // 2) 改昵称
        const u = await api('/users/me', {
          method: 'PUT',
          body: { nickname: this.profileNickname }
        });
        state.user.nickname = u.nickname;
        localStorage.setItem(USER_KEY, JSON.stringify(state.user));
        this.editDialog = false;
        this.notify('已保存');
      } catch (e) { this.fail(e); }
    },
    async loadPending() {
      try {
        this.pending = await api('/admin/review/tasks');
      } catch (e) {
        this.fail(e);
        if (e.status === 403) this.go('/posts');
      }
    },
    async review(item, action) {
      try {
        await api('/admin/review/' + item.postId, {
          method: 'POST',
          body: { action, remark: this.reviewRemark[item.postId] || '' }
        });
        this.notify(action === 'approve' ? '已通过' : '已删除');
        this.loadPending();
      } catch (e) { this.fail(e); }
    }
  },
  template: `
<div>
  <div class="topbar" v-if="loggedIn">
    <div class="brand">知屿校园<span class="ver">v23</span></div>
    <div class="nav">
      <a :href="'#/posts'" :class="{active: ['posts','post'].includes(route.name)}">博客</a>
      <a :href="'#/rooms'" :class="{active: ['rooms','chat'].includes(route.name)}">聊天室</a>
      <a :href="'#/search'" :class="{active: route.name === 'search'}">检索</a>
      <a :href="'#/me'" :class="{active: route.name === 'me'}">我的</a>
      <a v-if="uiAi" href="#" @click.prevent="aiOpen = !aiOpen" :class="{active: aiOpen}">AI</a>
      <a v-if="isAdmin" :href="'#/review'" :class="{active: route.name === 'review'}">审核台</a>
    </div>
    <div class="who">
      <span>{{ state.user ? state.user.nickname : '' }}
        <el-tag size="small" v-if="isAdmin" type="danger">管理员</el-tag>
      </span>
      <el-button size="small" @click="logout">退出</el-button>
    </div>
  </div>

  <!-- 登录 -->
  <div class="center-box" v-if="route.name === 'login'">
    <div class="login-card">
      <h1>知屿校园</h1>
      <div class="tip">校园信息智能平台 · 需求分析课程设计</div>
      <el-tabs v-model="tab">
        <el-tab-pane label="登录" name="login">
          <el-form label-position="top">
            <el-form-item label="学号 / 工号">
              <el-input v-model="loginForm.account" placeholder="如 20230001" />
            </el-form-item>
            <el-form-item label="口令">
              <el-input v-model="loginForm.password" type="password" show-password
                        @keyup.enter="doLogin" />
            </el-form-item>
            <el-button type="primary" style="width:100%" @click="doLogin">登录</el-button>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="注册" name="register">
          <el-form label-position="top">
            <el-form-item label="学号 / 工号">
              <el-input v-model="loginForm.account" placeholder="4~32 位字母或数字" />
            </el-form-item>
            <el-form-item label="昵称">
              <el-input v-model="loginForm.nickname" />
            </el-form-item>
            <el-form-item label="口令">
              <el-input v-model="loginForm.password" type="password" show-password
                        placeholder="至少 8 位，含字母和数字" />
            </el-form-item>
            <el-button type="primary" style="width:100%" @click="doRegister">注册</el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>

  <div class="page" v-else>
    <!-- 聊天室列表 -->
    <div v-if="route.name === 'rooms'">
      <div class="card">
        <div class="row">
          <h2 class="grow">聊天室</h2>
          <el-button type="primary" @click="roomDialog = true">创建聊天室</el-button>
        </div>
        <div class="sub">按标签筛选，点击进入聊天</div>
        <div class="row" style="margin-bottom:14px">
          <el-select v-model="filter.tagId" placeholder="全部标签" clearable style="width:200px"
                     @change="loadRooms">
            <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </div>
        <el-empty v-if="rooms.length === 0" description="还没有聊天室，创建一个吧" />
        <div v-for="r in rooms" :key="r.id" class="row"
             style="padding:12px 0;border-bottom:1px solid #eef1f6">
          <div class="grow">
            <div style="font-weight:600">{{ r.name }}</div>
            <div class="muted">{{ r.intro }} · {{ r.memberCount }} 人</div>
            <el-tag v-for="t in r.tags" :key="t" size="small" style="margin-right:6px">{{ t }}</el-tag>
          </div>
          <el-button size="small" @click="joinRoom(r)">进入</el-button>
        </div>
      </div>
    </div>

    <!-- 聊天界面 -->
    <div v-if="route.name === 'chat' && !currentRoom" class="card">
      <h2>无法打开聊天室</h2>
      <div class="sub">可能房间不存在，或你还没有加入</div>
      <el-button type="primary" @click="go('/rooms')">返回聊天室列表</el-button>
    </div>
    <div v-if="route.name === 'chat' && currentRoom">
      <div class="card">
        <div class="row">
          <h2 class="grow">{{ currentRoom.name }}</h2>
          <el-button size="small" @click="go('/rooms')">返回列表</el-button>
        </div>
        <div class="sub">{{ currentRoom.intro }} · {{ currentRoom.memberCount }} 人</div>
        <div class="msg-list">
          <el-empty v-if="messages.length === 0" description="还没有消息，说点什么" />
          <div v-for="m in messages" :key="m.id" class="msg-row"
               :class="{ mine: state.user && m.senderId === state.user.id }">
            <div class="avatar">{{ (m.senderNickname || '?').slice(0, 1) }}</div>
            <div class="msg-body">
              <div class="msg-meta">{{ m.senderNickname }} · {{ formatTime(m.createdAt) }}</div>
              <div class="bubble" v-if="m.msgType === 1">{{ m.content }}</div>
              <div v-else-if="m.msgType === 2" class="img-box">
                <a :href="m.content" target="_blank">
                  <img class="msg-img" :src="m.content" alt="图片" />
                </a>
                <a class="save-link" :href="m.content + '?download=1'" download>保存图片</a>
              </div>
              <a v-else class="file-bubble" :href="m.content" :download="fileName(m.content)">
                📎 {{ fileName(m.content) }}
              </a>
              <div class="recall" v-if="state.user && m.senderId === state.user.id"
                   @click="recall(m)">撤回</div>
            </div>
          </div>
        </div>
        <div class="pending-box" v-if="pending">
          <span class="pending-name">
            待发送：{{ pending.kind === 'image' ? '图片' : '文件' }} · {{ pending.name }}
            （{{ (pending.size / 1024).toFixed(1) }} KB）
          </span>
          <el-button size="small" @click="cancelPending">取消</el-button>
        </div>
        <div class="row" style="margin-top:12px">
          <input ref="fileInput" type="file" accept="image/*" style="display:none"
                 @change="onFileChosen($event, 'image')" />
          <input ref="docInput" type="file" style="display:none"
                 @change="onFileChosen($event, 'file')" />
          <el-button @click="pickFile('image')">图片</el-button>
          <el-button @click="pickFile('file')">文件</el-button>
          <el-input class="grow" v-model="msgText" placeholder="说点什么…（Enter 发送）"
                    @keyup.enter="sendMessage" />
          <el-button type="primary" :loading="uploading" @click="sendMessage">发送</el-button>
        </div>
      </div>
    </div>

    <!-- 帖子列表 -->
    <div v-if="route.name === 'posts'">
      <div class="card">
        <div class="row">
          <h2 class="grow">博客</h2>
          <el-button type="primary" @click="postDialog = true">发帖</el-button>
        </div>
        <div class="row" style="margin:12px 0">
          <el-select v-model="filter.boardId" placeholder="全部板块" clearable style="width:160px"
                     @change="loadPosts">
            <el-option v-for="b in boards" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
          <el-select v-model="filter.tagId" placeholder="全部标签" clearable style="width:160px"
                     @change="loadPosts">
            <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
          <el-radio-group v-model="filter.sort" @change="loadPosts">
            <el-radio-button label="latest">最新</el-radio-button>
            <el-radio-button label="hot">最热</el-radio-button>
          </el-radio-group>
        </div>
        <el-empty v-if="posts.length === 0" description="还没有帖子" />
        <div v-for="p in posts" :key="p.id" style="padding:12px 0;border-bottom:1px solid #eef1f6">
          <div class="post-title" @click="go('/posts/' + p.id)">{{ p.title }}</div>
          <div class="muted" style="margin:4px 0">{{ p.excerpt }}</div>
          <div class="row">
            <el-tag v-for="t in p.tags" :key="t" size="small">{{ t }}</el-tag>
            <span class="muted">{{ p.authorNickname }} · {{ p.boardName }} ·
              浏览 {{ p.viewCount }} · 赞 {{ p.likeCount }} · 收藏 {{ p.favoriteCount }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 帖子详情 -->
    <div v-if="route.name === 'post' && currentPost">
      <div class="card">
        <h2>{{ currentPost.title }}</h2>
        <div class="muted" style="margin:6px 0 14px">
          {{ currentPost.authorNickname }} · {{ currentPost.boardName }} ·
          浏览 {{ currentPost.viewCount }}
        </div>
        <div style="line-height:1.9;white-space:pre-wrap">{{ currentPost.body }}</div>
        <div class="row" style="margin-top:16px">
          <el-button :type="currentPost.liked ? 'danger' : 'default'" @click="toggleLike">
            赞 {{ currentPost.likeCount }}
          </el-button>
          <el-button :type="currentPost.favorited ? 'warning' : 'default'" @click="toggleFavorite">
            收藏 {{ currentPost.favoriteCount }}
          </el-button>
          <el-button @click="go('/posts')">返回</el-button>
        </div>
        <div v-if="aiResult" class="ai-panel" style="margin-top:16px">
          <b>AI 处理结果</b>（置信度 {{ aiResult.confidence }}，
          {{ aiResult.violation ? '判定可能存在违规' : '未发现违规' }}）
          <div>摘要：{{ aiResult.summary }}</div>
          <div>
            自动标签：
            <el-tag v-for="t in aiResult.tags" :key="t.tagId" size="small"
                    style="margin-right:6px">{{ t.name }}</el-tag>
          </div>
        </div>
      </div>

      <div class="card">
        <h2>回帖（{{ replies.length }}）</h2>
        <div v-for="r in replies" :key="r.id" style="padding:10px 0;border-bottom:1px solid #eef1f6">
          <div class="muted">{{ r.authorNickname }}</div>
          <div>{{ r.content }}</div>
        </div>
        <div class="row" style="margin-top:12px">
          <el-input class="grow" v-model="replyText" placeholder="写下你的回帖"
                    @keyup.enter="addReply" />
          <el-button type="primary" @click="addReply">回帖</el-button>
        </div>
      </div>
    </div>

    <!-- 检索 -->
    <div v-if="route.name === 'search'">
      <div class="card">
        <h2>检索</h2>
        <div class="sub">排序 = 0.5×相关度 + 0.3×热度 + 0.2×你的偏好</div>
        <div class="row" style="margin-bottom:14px">
          <el-input class="grow" v-model="searchQ" placeholder="输入关键词，如 高数"
                    @keyup.enter="doSearch" />
          <el-button type="primary" @click="doSearch">搜索</el-button>
        </div>
        <el-empty v-if="searchResults.length === 0" description="没有匹配结果" />
        <div v-for="item in searchResults" :key="item.type + item.id"
             style="padding:12px 0;border-bottom:1px solid #eef1f6">
          <div class="row">
            <span class="post-title" @click="openSearchResult(item)">{{ item.title }}</span>
            <el-tag size="small" type="info">{{ item.type === 'post' ? '帖子' : '聊天室' }}</el-tag>
            <span class="score-badge">score {{ item.score }}</span>
          </div>
          <div class="muted" style="margin:4px 0">{{ item.excerpt }}</div>
          <div class="muted">
            rel {{ item.rel }} · heat {{ item.heat }} · pref {{ item.pref }}
            <el-tag v-for="t in item.tags" :key="t" size="small" style="margin-left:6px">{{ t }}</el-tag>
          </div>
        </div>
      </div>
    </div>

    <!-- 个人中心 -->
    <div v-if="route.name === 'me'">
      <div class="card">
        <div class="row">
          <div class="avatar-lg">{{ (state.user && state.user.nickname || '?').slice(0, 1) }}</div>
          <div class="grow">
            <div style="font-size:18px;font-weight:600">{{ state.user ? state.user.nickname : '' }}</div>
            <div class="muted">
              发帖 {{ meStats.posts }} · 收藏 {{ meStats.favorites }} ·
              聊天室 {{ meStats.rooms }} · 点赞 {{ meStats.likes }} · 回帖 {{ meStats.replies }}
            </div>
          </div>
          <el-button @click="editDialog = true">编辑资料</el-button>
        </div>
      </div>

      <div class="card">
        <el-tabs v-model="meTab">
          <el-tab-pane label="我的帖子" name="posts">
            <el-empty v-if="myPosts.length === 0" description="还没发过帖子" />
            <div v-for="p in myPosts" :key="p.id" class="list-row">
              <div class="grow">
                <div class="post-title" @click="go('/posts/' + p.id)">{{ p.title }}</div>
                <div class="muted">{{ p.boardName }} · 浏览 {{ p.viewCount }} · 赞 {{ p.likeCount }}</div>
              </div>
              <el-tag size="small"
                      :type="p.status === 0 ? 'success' : (p.status === 1 ? 'warning' : 'info')">
                {{ p.statusText }}
              </el-tag>
            </div>
          </el-tab-pane>

          <el-tab-pane label="我的收藏" name="favorites">
            <el-empty v-if="myFavorites.length === 0" description="还没收藏内容" />
            <div v-for="p in myFavorites" :key="p.id" class="list-row">
              <div class="grow">
                <div class="post-title" @click="go('/posts/' + p.id)">{{ p.title }}</div>
                <div class="muted">{{ p.boardName }} · 赞 {{ p.likeCount }}</div>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="我的聊天室" name="rooms">
            <el-empty v-if="myRooms.length === 0" description="还没加入聊天室" />
            <div v-for="r in myRooms" :key="r.id" class="list-row">
              <div class="grow">
                <div class="post-title" @click="go('/rooms/' + r.id)">{{ r.name }}</div>
                <div class="muted">{{ r.memberCount }} 人 ·
                  {{ r.myRole === 2 ? '群主' : (r.myRole === 1 ? '管理员' : '成员') }}
                  <span v-if="r.myMuted === 1"> · 已禁言</span>
                </div>
              </div>
              <el-button size="small" @click="go('/rooms/' + r.id)">进入</el-button>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <!-- 审核台 -->
    <div v-if="route.name === 'review'">
      <div class="card">
        <h2>审核台</h2>
        <div class="sub">只处理待审内容；删除与恢复都会记录处置人</div>
        <el-empty v-if="pending.length === 0" description="没有待审内容" />
        <div v-for="item in pending" :key="item.postId"
             style="padding:14px 0;border-bottom:1px solid #eef1f6">
          <div style="font-weight:600">{{ item.title }}</div>
          <div class="muted" style="margin:4px 0">{{ item.excerpt }}</div>
          <div class="muted">
            作者 {{ item.authorNickname }} · AI 置信度 {{ item.confidence }} ·
            {{ item.violation ? '判定可能违规' : '未判定违规' }}
          </div>
          <div class="row" style="margin-top:8px">
            <el-input v-model="reviewRemark[item.postId]" placeholder="处置备注（可选）"
                      style="width:320px" />
            <el-button type="success" size="small" @click="review(item, 'approve')">通过</el-button>
            <el-button type="danger" size="small" @click="review(item, 'reject')">删除</el-button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 创建聊天室 -->
  <el-dialog v-model="roomDialog" title="创建聊天室" width="480px">
    <el-form label-position="top">
      <el-form-item label="名称"><el-input v-model="roomForm.name" /></el-form-item>
      <el-form-item label="简介"><el-input v-model="roomForm.intro" type="textarea" /></el-form-item>
      <el-form-item label="标签">
        <el-select v-model="roomForm.tagIds" multiple style="width:100%">
          <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="roomDialog = false">取消</el-button>
      <el-button type="primary" @click="createRoom">创建</el-button>
    </template>
  </el-dialog>

  <!-- 编辑资料 -->
  <el-dialog v-model="editDialog" title="编辑资料" width="420px">
    <el-form label-position="top">
      <el-form-item label="昵称">
        <el-input v-model="profileNickname" maxlength="32" />
      </el-form-item>
      <el-form-item label="原口令（改密码时填）">
        <el-input v-model="pwdOld" type="password" show-password placeholder="不改密码就留空" />
      </el-form-item>
      <el-form-item label="新口令">
        <el-input v-model="pwdNew" type="password" show-password
                  placeholder="8 位以上，含字母和数字" />
      </el-form-item>
      <el-form-item label="确认新口令">
        <el-input v-model="pwdConfirm" type="password" show-password />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="editDialog = false">取消</el-button>
      <el-button type="primary" @click="saveProfile">保存</el-button>
    </template>
  </el-dialog>

  <!-- 发帖 -->
  <el-dialog v-model="postDialog" title="发帖" width="560px">
    <el-form label-position="top">
      <el-form-item label="板块">
        <el-select v-model="postForm.boardId" style="width:100%">
          <el-option v-for="b in boards" :key="b.id" :label="b.name" :value="b.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="标题"><el-input v-model="postForm.title" maxlength="100" /></el-form-item>
      <el-form-item label="正文">
        <el-input v-model="postForm.body" type="textarea" :rows="6" maxlength="20000" />
      </el-form-item>
      <el-form-item label="标签（最多 5 个）">
        <el-select v-model="postForm.tagIds" multiple style="width:100%">
          <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="postDialog = false">取消</el-button>
      <el-button type="primary" @click="createPost">发布</el-button>
    </template>
  </el-dialog>

  <!-- AI 助手 -->
  <div v-if="uiAi" class="ai-fab" :style="fabStyle" @mousedown="startFabDrag"
       :title="aiOpen ? '收起' : '打开 AI 助手（可拖动）'">
    {{ aiOpen ? '×' : 'AI' }}
  </div>

  <div v-if="uiAi && aiOpen" class="ai-box" ref="aiBox" :style="aiStyle">
    <div class="ai-head" @mousedown="startDrag">
      <div class="ai-head-row">
        <span>AI 助手</span>
        <span class="ai-drag-hint">按住拖动 · <a @click.stop="resetAIPos" href="#">复位</a></span>
      </div>
      <span class="ai-sub">{{ aiContextText() }}</span>
    </div>
    <div class="ai-list" ref="aiList">
      <div v-if="aiMessages.length === 0" class="ai-empty">
        试试问我：<br>
        · 有哪些聊天室<br>
        · 看看最新帖子<br>
        · 帮我搜一下高数<br>
        · 总结一下当前聊天室<br>
        · 这篇帖子讲了什么
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
</div>
`
};

/**
 * 启动引导：手机上 Element Plus（1 MB）可能加载失败或超时，
 * 直接 createApp 会抛 "Can't find variable: ElementPlus" 然后白屏。
 * 这里先确认依赖就绪，没就绪就重试加载，实在不行给提示。
 */
function boot(tries) {
  const hasVue = typeof window.Vue !== 'undefined' && !!window.Vue.createApp;
  const hasEP = typeof window.ElementPlus !== 'undefined';

  if (hasVue && hasEP) {
    window.Vue.createApp(app).use(window.ElementPlus).mount('#app');
    const tip = document.getElementById('boot-tip');
    if (tip) tip.remove();
    return;
  }

  if (tries <= 0) {
    const tip = document.getElementById('boot-tip');
    if (tip) {
      tip.innerHTML = '界面库加载失败。<br>请检查网络后刷新，或点这里 <a href="javascript:location.reload()">重新加载</a>。';
      tip.style.color = '#a8071a';
    }
    return;
  }

  // 缺谁补谁
  if (!hasEP) {
    const s = document.createElement('script');
    s.src = '/vendor/element-plus.full.js?retry=' + Date.now();
    document.body.appendChild(s);
  }
  setTimeout(() => boot(tries - 1), 1200);
}

boot(6);

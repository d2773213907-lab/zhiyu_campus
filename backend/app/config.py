"""全局配置。

所有可调参数集中在这里，改端口、改数据库都不用翻代码。
"""

import os

# 可选：从 backend/.env 读取本地配置（密钥放这里，不进 Git）
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except Exception:
    pass

# ---------------------------------------------------------------- 服务
HOST = os.getenv("APP_HOST", "0.0.0.0")
PORT = int(os.getenv("APP_PORT", "8000"))

# ---------------------------------------------------------------- 数据库
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3307"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "zhiyu_campus")

# ---------------------------------------------------------------- 认证
# 与 Java 版使用同一个密钥，方便两边令牌互通
JWT_SECRET = os.getenv(
    "JWT_SECRET", "zhiyu-campus-dev-secret-key-32bytes!!"
).encode("utf-8")
ACCESS_MINUTES = 120      # 访问令牌有效期
REFRESH_DAYS = 7          # 刷新令牌有效期
MAX_LOGIN_FAILURES = 5    # 连续失败几次锁定
LOCK_MINUTES = 10         # 锁定时长

# ---------------------------------------------------------------- 检索
REL_WEIGHT = 0.5          # 相关度权重
HEAT_WEIGHT = 0.3         # 热度权重
PREF_WEIGHT = 0.2         # 偏好权重
RECENCY_LAMBDA = 0.05     # 热度时间衰减系数
RECALL_LIMIT = 200        # 召回上限
DEFAULT_LIMIT = 20        # 默认返回条数

# ---------------------------------------------------------------- 智能体
AI_ENABLED = os.getenv("AI_ENABLED", "false").lower() == "true"
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.deepseek.com/v1")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-chat")
AI_TIMEOUT = 20

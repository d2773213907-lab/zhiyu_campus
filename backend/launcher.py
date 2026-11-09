"""知屿校园 · 一键启动器

用法（在 backend 目录下）：
    python launcher.py

它会依次做这些事：
  1. 检查 Python 版本
  2. 没有虚拟环境就创建，并安装依赖
  3. 自动探测 MySQL 端口（3306 / 3307）
  4. 数据库不存在就建库，表不存在就导入 schema.sql
  5. 启动服务，并打印本机与局域网地址

任何一步失败都会给出中文原因和解决办法，不会只丢一个技术报错。
"""

import os
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "Scripts", "python.exe")
SCHEMA = os.path.join(os.path.dirname(HERE), "schema.sql")
MIRROR = "https://mirrors.aliyun.com/pypi/simple/"

DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "zhiyu_campus")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")


def say(msg=""):
    print(msg, flush=True)


def title(msg):
    say()
    say("=" * 56)
    say("  " + msg)
    say("=" * 56)


# ------------------------------------------------------------------ 1. 环境
def ensure_venv():
    """如果在系统 Python 里运行，就切换到虚拟环境重新执行自己。"""
    if os.path.normcase(sys.prefix).startswith(os.path.normcase(HERE)):
        return                                    # 已经在 venv 里
    if not os.path.exists(VENV_PY):
        title("第一次运行：创建虚拟环境")
        r = subprocess.run([sys.executable, "-m", "venv", os.path.join(HERE, ".venv")])
        if r.returncode != 0:
            say("[失败] 创建虚拟环境失败。请确认 Python 安装完整（需要 venv 模块）。")
            sys.exit(1)

    say("检查依赖...")
    missing = subprocess.run(
        [VENV_PY, "-c", "import fastapi, uvicorn, pymysql, jwt, bcrypt, multipart"],
        capture_output=True).returncode != 0
    if missing:
        say("安装依赖（阿里云镜像，约 30 秒）...")
        r = subprocess.run(
            [VENV_PY, "-m", "pip", "install", "-q", "--disable-pip-version-check",
             "-i", MIRROR, "-r", os.path.join(HERE, "requirements.txt")])
        if r.returncode != 0:
            say("[失败] 依赖安装失败，请检查网络后重试。")
            sys.exit(1)

    # 用虚拟环境的解释器重新运行本脚本
    sys.exit(subprocess.run([VENV_PY, os.path.abspath(__file__)] + sys.argv[1:]).returncode)


def check_python():
    if sys.version_info < (3, 10):
        say(f"[失败] 需要 Python 3.10 以上，当前是 {sys.version.split()[0]}")
        sys.exit(1)


# ------------------------------------------------------------------ 2. 数据库
def try_connect(port):
    import pymysql
    return pymysql.connect(
        host=DB_HOST, port=port, user=DB_USER, password=DB_PASSWORD,
        charset="utf8mb4", connect_timeout=3)


def detect_mysql():
    """优先用配置端口；连不上就试 3306。返回可用端口或 None。"""
    preferred = int(os.getenv("DB_PORT", "3307"))
    for port in (preferred, 3306, 3307):
        try:
            conn = try_connect(port)
            conn.close()
            return port
        except Exception:
            continue
    return None


def ensure_database(port):
    import pymysql

    conn = try_connect(port)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema=%s AND table_name='user'", (DB_NAME,))
            ready = cur.fetchone()[0] > 0

        if not ready:
            title("初始化数据库")
            if not os.path.exists(SCHEMA):
                say(f"[失败] 找不到建库脚本：{SCHEMA}")
                sys.exit(1)
            with open(SCHEMA, encoding="utf-8") as fh:
                sql = fh.read()
            # 用分号切分语句（本项目 schema 里没有存储过程，切分安全）
            statements = [s.strip() for s in sql.split(";") if s.strip()]
            with conn.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                    "DEFAULT CHARSET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
                cur.execute(f"USE `{DB_NAME}`")
                done = 0
                for stmt in statements:
                    if stmt.upper().startswith(("SET ", "USE ")):
                        continue
                    try:
                        cur.execute(stmt)
                        done += 1
                    except Exception as exc:
                        say(f"  跳过一条语句：{str(exc)[:80]}")
            conn.commit()
            say(f"  已导入 {done} 条语句")
        else:
            say(f"数据库 {DB_NAME} 已就绪")

        conn.select_db(DB_NAME)
        return True
    finally:
        conn.close()


def setup_database():
    title("检查数据库")
    port = detect_mysql()
    if port is None:
        say("[失败] 连不上 MySQL。请确认：")
        say("  1) MySQL 服务已启动")
        say(f"  2) 账号 {DB_USER} 的密码正确（可用环境变量 DB_PASSWORD 指定）")
        say("  3) 端口是 3306 或 3307")
        say()
        say("如果 MySQL 在别的端口，先执行：")
        say("  set DB_PORT=3306")
        sys.exit(1)

    say(f"MySQL 端口：{port}")
    os.environ["DB_PORT"] = str(port)
    if ensure_database(port):
        say("数据库检查通过")


# ------------------------------------------------------------------ 3. 启动
def local_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    return [ip for ip in ips if not ip.startswith("127.")]


def main():
    title("知屿校园 · 启动器")
    check_python()
    ensure_venv()
    setup_database()

    port = int(os.getenv("APP_PORT", "8080"))
    host = os.getenv("APP_HOST", "0.0.0.0")

    title("启动服务")
    say(f"  本机访问：  http://127.0.0.1:{port}")
    for ip in local_ips():
        say(f"  局域网访问：http://{ip}:{port}")
    say()
    say("  关闭这个窗口 = 停止服务")
    say("=" * 56)
    say()

    import uvicorn
    uvicorn.run("app.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()

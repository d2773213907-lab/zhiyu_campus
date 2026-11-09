"""数据库访问。

用最朴素的方式：每次请求拿一个连接，用完关掉。
课程项目并发不高，这样最好读、最好懂——没有 ORM 的隐式行为。
"""

from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from . import config


def _connect():
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )


@contextmanager
def conn():
    """给只读查询用：自动提交/回滚、自动关闭。"""
    c = _connect()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def query_all(sql: str, args: tuple = ()) -> list[dict]:
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()


def query_one(sql: str, args: tuple = ()) -> dict | None:
    rows = query_all(sql, args)
    return rows[0] if rows else None


def execute(sql: str, args: tuple = ()) -> int:
    """执行写操作，返回自增主键（INSERT）或受影响行数。"""
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(sql, args)
            return cur.lastrowid or cur.rowcount

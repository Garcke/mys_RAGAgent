"""
SQLite 数据库初始化与操作
按照设计文档 3.2 节 schema 实现
"""
import sqlite3
import json
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "rag.db")


def init_db():
    """初始化数据库，创建表结构"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS posts (
            post_id     TEXT PRIMARY KEY,
            game_id     INTEGER,
            subject     TEXT,
            author_name TEXT,
            forum_name  TEXT,
            created_at  INTEGER,
            like_num    INTEGER DEFAULT 0,
            view_num    INTEGER DEFAULT 0,
            is_official BOOLEAN DEFAULT 0,
            topic_ids   TEXT,
            version_tag TEXT,
            quality_score REAL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS post_assets (
            asset_id        TEXT PRIMARY KEY,
            post_id         TEXT NOT NULL,
            asset_type      TEXT NOT NULL,
            content_summary TEXT,
            original_url    TEXT,
            metadata        TEXT,
            doc_id          TEXT,
            FOREIGN KEY (post_id) REFERENCES posts(post_id)
        );

        CREATE INDEX IF NOT EXISTS idx_assets_post_id ON post_assets(post_id);
        CREATE INDEX IF NOT EXISTS idx_posts_game_id  ON posts(game_id);
        """)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_post(post: dict):
    """插入或更新帖子元数据"""
    with get_conn() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO posts
            (post_id, game_id, subject, author_name, forum_name,
             created_at, like_num, view_num, is_official, topic_ids,
             version_tag, quality_score)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            post["post_id"],
            post.get("game_id"),
            post.get("subject"),
            post.get("author_name"),
            post.get("forum_name"),
            post.get("created_at"),
            post.get("like_num", 0),
            post.get("view_num", 0),
            1 if post.get("is_official") else 0,
            json.dumps(post.get("topic_ids", []), ensure_ascii=False),
            post.get("version_tag"),
            post.get("quality_score", 0.0),
        ))


def upsert_asset(asset: dict):
    """插入或更新资产记录"""
    with get_conn() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO post_assets
            (asset_id, post_id, asset_type, content_summary,
             original_url, metadata, doc_id)
        VALUES (?,?,?,?,?,?,?)
        """, (
            asset["asset_id"],
            asset["post_id"],
            asset["asset_type"],
            asset.get("content_summary"),
            asset.get("original_url"),
            json.dumps(asset.get("metadata", {}), ensure_ascii=False),
            asset.get("doc_id"),
        ))


def get_post(post_id: str) -> dict | None:
    """按 post_id 查询帖子"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM posts WHERE post_id=?", (post_id,)
        ).fetchone()
        return dict(row) if row else None


def get_assets_by_post(post_id: str) -> list:
    """查询某帖子下的所有资产"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM post_assets WHERE post_id=?", (post_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_stats() -> dict:
    """统计知识库数量"""
    with get_conn() as conn:
        posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        docs  = conn.execute("SELECT COUNT(*) FROM post_assets").fetchone()[0]
        by_type = {}
        for row in conn.execute(
            "SELECT asset_type, COUNT(*) as cnt FROM post_assets GROUP BY asset_type"
        ).fetchall():
            by_type[row[0]] = row[1]
        return {"posts": posts, "docs": docs, "by_type": by_type}


def post_already_indexed(post_id: str) -> bool:
    """检查帖子是否已入库（用于去重）"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM posts WHERE post_id=?", (post_id,)
        ).fetchone()
        return row is not None

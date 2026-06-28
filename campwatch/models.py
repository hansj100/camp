import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'campwatch.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            telegram_token   TEXT DEFAULT NULL,
            telegram_chat_id TEXT DEFAULT NULL,
            is_approved INTEGER DEFAULT 0,
            is_admin    INTEGER DEFAULT 0,
            level       INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS watch_conditions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            camp_name TEXT NOT NULL,
            site_name TEXT,
            check_in TEXT NOT NULL,
            check_out TEXT NOT NULL,
            nights INTEGER DEFAULT 1,
            zone_id TEXT DEFAULT NULL,
            source TEXT DEFAULT 'foresttrip',
            active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS notify_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condition_id INTEGER NOT NULL,
            message TEXT,
            notified_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (condition_id) REFERENCES watch_conditions(id)
        );

        CREATE TABLE IF NOT EXISTS favorites (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            zone_id     TEXT    NOT NULL,
            campsite    TEXT    NOT NULL,
            sido        TEXT    DEFAULT '',
            created_at  TEXT    DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, zone_id)
        );
    ''')
    conn.commit()

    # 마이그레이션: source 컬럼 추가 (기존 DB 호환)
    try:
        conn.execute("ALTER TABLE watch_conditions ADD COLUMN source TEXT DEFAULT 'foresttrip'")
        conn.commit()
    except Exception:
        pass  # 이미 존재

    # 관리자 계정 없으면 자동 생성
    import bcrypt
    existing = conn.execute("SELECT id FROM users WHERE is_admin=1").fetchone()
    if not existing:
        pw = bcrypt.hashpw(b"campwatch1234", bcrypt.gensalt()).decode()
        conn.execute(
            "INSERT INTO users (username, password, is_approved, is_admin) VALUES (?,?,1,1)",
            ("admin", pw)
        )
        conn.commit()

    conn.close()

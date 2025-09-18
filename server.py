# server.py
# Execute: uvicorn server:app --host 0.0.0.0 --port 8000

import sqlite3
import hashlib
import threading
import json
from typing import Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse

DB_FILE = "rubyruby.db"
lock = threading.Lock()
app = FastAPI()

# ---------------- Database ----------------
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            owner TEXT,
            contact TEXT,
            PRIMARY KEY(owner, contact)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            group_id INTEGER,
            username TEXT,
            PRIMARY KEY(group_id, username)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT,
            target_type TEXT,
            target TEXT,
            text TEXT,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn

conn = init_db()

# ---------------- Utilities ----------------
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# ---------------- HTTP Routes ----------------
@app.post("/register")
def register(payload: Dict):
    username = payload.get("username")
    password = payload.get("password")
    if not username or not password:
        raise HTTPException(400, "username and password required")

    with lock:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE username=?", (username,))
        if cur.fetchone():
            return JSONResponse({"ok": False, "error": "user exists"})
        cur.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hash_password(password)))
        conn.commit()
    return {"ok": True}

@app.post("/login")
def login(payload: Dict):
    username = payload.get("username")
    password = payload.get("password")
    if not username or not password:
        raise HTTPException(400, "username and password required")

    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    if not row or row[0] != hash_password(password):
        return JSONResponse({"ok": False, "error": "invalid credentials"})
    return {"ok": True, "token": username}

@app.post("/add_contact")
def add_contact(payload: Dict):
    owner = payload.get("owner")
    contact = payload.get("contact")
    if not owner or not contact:
        raise HTTPException(400, "owner and contact required")
    with lock:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO contacts (owner, contact) VALUES (?, ?)", (owner, contact))
        conn.commit()
    return {"ok": True}

@app.post("/create_group")
def create_group(payload: Dict):
    name = payload.get("name")
    owner = payload.get("owner")
    if not name or not owner:
        raise HTTPException(400, "name and owner required")
    with lock:
        cur = conn.cursor()
        cur.execute("INSERT INTO groups (name) VALUES (?)", (name,))
        gid = cur.lastrowid
        cur.execute("INSERT INTO group_members (group_id, username) VALUES (?, ?)", (gid, owner))
        conn.commit()
    return {"ok": True, "group_id": gid}

@app.post("/join_group")
def join_group(payload: Dict):
    gid = payload.get("group_id")
    username = payload.get("user")
    if not gid or not username:
        raise HTTPException(400, "group_id and user required")
    with lock:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO group_members (group_id, username) VALUES (?, ?)", (gid, username))
        conn.commit()
    return {"ok": True}

@app.get("/contacts/{username}")
def get_contacts(username: str):
    cur = conn.cursor()
    cur.execute("SELECT contact FROM contacts WHERE owner=?", (username,))
    contacts = [r[0] for r in cur.fetchall()]
    return {"contacts": contacts}

@app.get("/groups/{username}")
def get_groups(username: str):
    cur = conn.cursor()
    cur.execute("""
        SELECT g.id, g.name FROM groups g
        JOIN group_members gm ON g.id=gm.group_id
        WHERE gm.username=?
    """, (username,))
    groups = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
    return {"groups": groups}

@app.get("/messages/{username}/{target_type}/{target}")
def get_messages(username: str, target_type: str, target: str):
    cur = conn.cursor()
    if target_type == "user":
        cur.execute("""
            SELECT sender, text, ts FROM messages
            WHERE (sender=? AND target=? AND target_type='user')
               OR (sender=? AND target=? AND target_type='user')
            ORDER BY id
        """, (username, target, target, username))
    else:
        cur.execute("""
            SELECT sender, text, ts FROM messages
            WHERE target_type='group' AND target=?
            ORDER BY id
        """, (target,))
    msgs = [{"sender": r[0], "text": r[1], "ts": r[2]} for r in cur.fetchall()]
    return {"messages": msgs}

# ---------------- WebSocket ----------------
class WSManager:
    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}
        self.lock = threading.Lock()

    async def connect(self, username: str, ws: WebSocket):
        await ws.accept()
        with self.lock:
            self.connections[username] = ws

    def disconnect(self, username: str):
        with self.lock:
            self.connections.pop(username, None)

    async def send(self, username: str, message: dict):
        ws = self.connections.get(username)
        if ws:
            try:
                await ws.send_text(json.dumps(message))
            except:
                pass

    async def broadcast_group(self, group_id: str, message: dict):
        cur = conn.cursor()
        cur.execute("SELECT username FROM group_members WHERE group_id=?", (group_id,))
        members = [r[0] for r in cur.fetchall()]
        for m in members:
            await self.send(m, message)

ws_manager = WSManager()

@app.websocket("/ws/{token}")
async def websocket_endpoint(ws: WebSocket, token: str):
    username = token
    await ws_manager.connect(username, ws)
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "message":
                target_type = msg.get("target_type")
                target = str(msg.get("target"))
                text = msg.get("text")
                with lock:
                    cur = conn.cursor()
                    cur.execute("INSERT INTO messages (sender, target_type, target, text) VALUES (?, ?, ?, ?)",
                                (username, target_type, target, text))
                    conn.commit()
                payload = {"type": "message", "from": username, "to": target, "text": text, "target_type": target_type}
                if target_type == "user":
                    await ws_manager.send(target, payload)
                else:
                    await ws_manager.broadcast_group(target, payload)
    except WebSocketDisconnect:
        ws_manager.disconnect(username)
    except Exception:
        ws_manager.disconnect(username)

# -*- coding: utf-8 -*-
"""
账号与登录态。

  - 账号存在项目根目录的 users.json，里面只有「随机盐 + PBKDF2 摘要」，没有明文密码。
  - 登录成功后发一个随机 token，由 api.py 写进 HttpOnly Cookie；会话表保存在内存，
    重启服务后需要重新登录（故意不落盘，避免 Cookie 长期有效带来风险）。
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "users.json")

ITERATIONS = 120000
SESSION_TTL = 7 * 24 * 3600  # 7 天
USERNAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5-]{2,32}$")
MIN_PASSWORD = 6

_lock = threading.Lock()
_sessions = {}  # token -> {"username": str, "expires": float}


def _load():
    if not os.path.exists(DB_PATH):
        return {}
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(users):
    tmp = DB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DB_PATH)


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt), ITERATIONS).hex()
    return salt, digest


def verify_password(password, record):
    if not record:
        return False
    _, digest = hash_password(password, record.get("salt") or "")
    return hmac.compare_digest(digest, record.get("hash") or "")


def _check_credentials(username, password):
    if not USERNAME_RE.match(username or ""):
        return "用户名需为 2~32 位中文、字母、数字、下划线或短横线"
    if len(password or "") < MIN_PASSWORD:
        return "密码至少 %d 位" % MIN_PASSWORD
    return ""


def register(username, password):
    username = (username or "").strip()
    err = _check_credentials(username, password)
    if err:
        return False, err
    with _lock:
        users = _load()
        if username.lower() in {k.lower() for k in users}:
            return False, "该用户名已被占用"
        salt, digest = hash_password(password)
        users[username] = {"salt": salt, "hash": digest, "iterations": ITERATIONS,
                           "createdAt": int(time.time())}
        _save(users)
    return True, ""


def start_session(username):
    token = secrets.token_urlsafe(32)
    with _lock:
        _prune()
        _sessions[token] = {"username": username, "expires": time.time() + SESSION_TTL}
    return token


def login(username, password):
    username = (username or "").strip()
    with _lock:
        record = _load().get(username)
    if not record or not verify_password(password or "", record):
        return False, "用户名或密码错误"
    return True, start_session(username)


def logout(token):
    with _lock:
        _sessions.pop(token, None)


def _prune():
    now = time.time()
    for tk in [t for t, s in _sessions.items() if s["expires"] < now]:
        _sessions.pop(tk, None)


def username_of(token):
    if not token:
        return ""
    with _lock:
        _prune()
        sess = _sessions.get(token)
        if not sess:
            return ""
        sess["expires"] = time.time() + SESSION_TTL  # 滑动续期
        return sess["username"]


def change_password(username, old_password, new_password):
    err = _check_credentials(username, new_password)
    if err:
        return False, err
    with _lock:
        users = _load()
        record = users.get(username)
        if not record or not verify_password(old_password or "", record):
            return False, "原密码不正确"
        salt, digest = hash_password(new_password)
        users[username] = dict(record, salt=salt, hash=digest, iterations=ITERATIONS,
                               updatedAt=int(time.time()))
        _save(users)
        for tk in [t for t, s in _sessions.items() if s["username"] == username]:
            _sessions.pop(tk, None)  # 改密后其他设备上的会话全部作废
    return True, ""

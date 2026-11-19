# -*- coding: utf-8 -*-
"""
本地文件存储：角色提示词（md 文件）+ 历史对话（json 文件）

  prompts/<角色>.md     —— 有文件就是「已自定义」，删掉即回到 config.js 里的默认设定
  history/<用户>.json   —— {角色id: [{role, content, ts}, ...]}

全部读写都过 threading.Lock，写文件先写 .tmp 再 os.replace，
避免两个请求同时落盘时把文件写成半截。
"""
import json
import os
import re
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
PROMPT_DIR = os.path.join(ROOT, "prompts")
HISTORY_DIR = os.path.join(ROOT, "history")
MAX_MESSAGES = 400  # 单个角色最多留 400 条，约 200 轮

_lock = threading.Lock()
_KEY_RE = re.compile(r"^[A-Za-z0-9_一-龥-]{1,40}$")


def safe_key(name):
    """角色 id 和用户名都会直接当文件名，先挡掉 ../ 和路径分隔符。"""
    name = str(name or "")
    return name if _KEY_RE.match(name) else ""


def _atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# ---------------- 角色提示词 ----------------
def prompt_path(role):
    return os.path.join(PROMPT_DIR, role + ".md")


def read_prompt(role):
    """返回 (内容, 是否存在)。文件不存在时内容是空串。"""
    key = safe_key(role)
    if not key:
        return "", False
    path = prompt_path(key)
    if not os.path.isfile(path):
        return "", False
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip(), True


def read_all_prompts(roles):
    out = {}
    for role in roles:
        text, exists = read_prompt(role)
        if exists and text:
            out[role] = text
    return out


def write_prompt(role, content):
    key = safe_key(role)
    if not key:
        return False
    content = str(content or "").strip()
    if not content:
        delete_prompt(key)
        return True
    if len(content) > 20000:
        return False
    with _lock:
        os.makedirs(PROMPT_DIR, exist_ok=True)
        _atomic_write(prompt_path(key), content + "\n")
    return True


def delete_prompt(role):
    key = safe_key(role)
    if not key:
        return False
    path = prompt_path(key)
    with _lock:
        if os.path.isfile(path):
            os.remove(path)
            return True
    return False


# ---------------- 历史对话 ----------------
def history_path(username):
    return os.path.join(HISTORY_DIR, username + ".json")


def _load_history(username):
    path = history_path(username)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def read_history(username, role):
    key = safe_key(username)
    if not key:
        return []
    msgs = _load_history(key).get(str(role), [])
    return msgs if isinstance(msgs, list) else []


def _clean(messages):
    """只保留白名单字段，长度也掐掉，防止前端往历史文件里塞垃圾。"""
    out = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = str(m.get("content") or "")[:20000]
        if not content:
            continue
        item = {"role": role, "content": content}
        ts = m.get("ts")
        if isinstance(ts, (int, float)):
            item["ts"] = int(ts)
        if m.get("search"):
            item["search"] = True
        if m.get("error"):
            item["error"] = True
        if m.get("model"):
            item["model"] = str(m["model"])[:60]
        tools = m.get("tools")
        if isinstance(tools, list) and tools:
            item["tools"] = [t for t in tools[:5] if isinstance(t, dict)]
        rag_hits = m.get("rag")
        if isinstance(rag_hits, list) and rag_hits:
            # RAG 引用的来源：只留文档名、段号和相似度，够前端复现引用即可
            item["rag"] = [{"name": str(h.get("name") or "")[:60],
                            "i": h.get("i"), "score": h.get("score")}
                           for h in rag_hits[:6] if isinstance(h, dict)]
        cache = m.get("cache")
        if isinstance(cache, dict) and cache.get("hit"):
            # 命中要留档，否则刷新后分不清哪条答案其实没调模型
            item["cache"] = {"hit": True, "score": cache.get("score"),
                             "question": str(cache.get("question") or "")[:200]}
        out.append(item)
    return out[-MAX_MESSAGES:]


def write_history(username, role, messages):
    key = safe_key(username)
    if not key:
        return False
    with _lock:
        data = _load_history(key)
        cleaned = _clean(messages if isinstance(messages, list) else [])
        if cleaned:
            data[str(role)] = cleaned
        else:
            data.pop(str(role), None)
        os.makedirs(HISTORY_DIR, exist_ok=True)
        _atomic_write(history_path(key), json.dumps(data, ensure_ascii=False, indent=1))
    return True


def clear_history(username, role=None):
    key = safe_key(username)
    if not key:
        return False
    with _lock:
        data = _load_history(key)
        if role is None or str(role) in ("", "all"):
            data = {}
        else:
            data.pop(str(role), None)
        if data:
            _atomic_write(history_path(key), json.dumps(data, ensure_ascii=False, indent=1))
        elif os.path.isfile(history_path(key)):
            os.remove(history_path(key))
    return True

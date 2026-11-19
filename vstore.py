# -*- coding: utf-8 -*-
"""
极简向量库（vector store）：把"向量 + 原文 + 元数据"按集合存成本地 JSON 文件。

一份集合 = 一个文件：kb/collections/<集合名>.json
  {
    "name": "qa",
    "model": "text-embedding-v3",
    "dim": 1024,
    "createdAt": 1793600000,
    "updatedAt": 1793600000,
    "items": [
      {
        "id": "q20261104120000-a3f1",     ← 主键，只允许安全字符
        "text": "检索阈值默认是多少",       ← 原文，用来做完全相同判断和展示
        "vec": [0.0123, -0.0456, ...],    ← 向量，四舍五入到 5 位小数控制体积
        "meta": {"scope": "…", "answer": "…"},  ← 任意可 JSON 化的元数据，检索时能当过滤条件
        "hits": 3,
        "createdAt": 1793600000,
        "updatedAt": 1793600000
      }
    ]
  }

和 kb/<文档id>.json 是同一套思路（本地文件持久化），区别是：
  · 文档库是"一份文档一个文件"，改动要整份重写；
  · 集合库支持**单条增量** upsert / delete，不用重写整个文件之外的东西，
    适合问答缓存这种"一条一条往里加、还要按条件删"的场景。

没有 numpy、没有 faiss、没有任何第三方依赖：余弦用纯 Python 循环算，
几千条以内完全够用（一条 1024 维 ≈ 10 KB，一次全表扫描几毫秒）。
"""
import json
import math
import os
import re
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
COL_DIR = os.path.join(ROOT, "kb", "collections")

# 集合名直接当文件名，所以只允许小写字母开头的短标识，杜绝 ../ 这类路径注入
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
ITEM_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,48}$")

_lock = threading.Lock()


class StoreError(Exception):
    """给上层直接转成 4xx 的错误。"""


def _atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def col_path(name):
    if not NAME_RE.match(str(name or "")):
        raise StoreError("非法的集合名")
    return os.path.join(COL_DIR, name + ".json")


def exists(name):
    return os.path.isfile(col_path(name))


def load(name):
    """读集合；文件不存在返回空骨架（不落盘，等第一次写再建）。"""
    path = col_path(name)
    if not os.path.isfile(path):
        return {"name": name, "model": "", "dim": 0,
                "createdAt": int(time.time()), "updatedAt": 0, "items": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"name": name, "model": "", "dim": 0,
                "createdAt": int(time.time()), "updatedAt": 0, "items": []}
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise StoreError("集合文件坏了：kb/collections/%s.json" % name)
    data["items"] = [i for i in data["items"]
                     if isinstance(i, dict) and ITEM_ID_RE.match(str(i.get("id") or ""))]
    data.setdefault("createdAt", int(time.time()))
    return data


def save(coll):
    coll["updatedAt"] = int(time.time())
    path = col_path(coll["name"])
    with _lock:
        os.makedirs(COL_DIR, exist_ok=True)
        _atomic_write(path, json.dumps(coll, ensure_ascii=False))
    return coll


def upsert(name, items, model="", dim=0, max_items=0):
    """按 id 增量写入：已存在就覆盖，不存在就追加。返回 {added, updated, dropped}。

    max_items 超了按"最久没被用到"淘汰（LRU：updatedAt 小的先走）。
    """
    items = [i for i in (items or []) if isinstance(i, dict) and ITEM_ID_RE.match(str(i.get("id") or ""))]
    if not items:
        raise StoreError("没有可写入的条目")
    now = int(time.time())
    coll = load(name)
    if model:
        coll["model"] = model
    if dim:
        coll["dim"] = int(dim)
    by_id = {i["id"]: n for n, i in enumerate(coll["items"])}
    added = updated = 0
    for item in items:
        vec = item.get("vec") or []
        if not isinstance(vec, list) or not vec:
            raise StoreError("条目缺少向量")
        entry = {"id": item["id"], "text": str(item.get("text") or "")[:4000],
                 "vec": [round(float(v), 5) for v in vec],
                 "meta": item.get("meta") if isinstance(item.get("meta"), dict) else {},
                 "hits": int(item.get("hits") or 0),
                 "createdAt": now, "updatedAt": now}
        if item["id"] in by_id:
            old = coll["items"][by_id[item["id"]]]
            entry["createdAt"] = old.get("createdAt") or now
            entry["hits"] = int(old.get("hits") or 0) + int(entry["hits"])
            coll["items"][by_id[item["id"]]] = entry
            updated += 1
        else:
            coll["items"].append(entry)
            added += 1
    dropped = 0
    if max_items and len(coll["items"]) > max_items:
        coll["items"].sort(key=lambda e: (e.get("updatedAt") or 0, e.get("createdAt") or 0))
        dropped = len(coll["items"]) - max_items
        coll["items"] = coll["items"][dropped:]
    save(coll)
    return {"added": added, "updated": updated, "dropped": dropped, "total": len(coll["items"])}


def clear(name):
    """清空一个集合（保留文件，items 置空）。返回清掉的条数。"""
    coll = load(name)
    removed = len(coll["items"])
    coll["items"] = []
    save(coll)
    return removed


def _meta_match(meta, where):
    for key, want in (where or {}).items():
        got = meta.get(key)
        if isinstance(got, list):
            # 元数据里存的是列表（比如引用了哪几份文档）时，按"包含"匹配
            if isinstance(want, (list, tuple)):
                if not any(w in got for w in want):
                    return False
            elif want not in got:
                return False
        elif got != want:
            return False
    return True


def delete(name, ids=None, where=None):
    """按 id 删，或按 meta 条件删（两者都给时取交集）。返回删除条数。"""
    coll = load(name)
    id_set = set(ids or [])
    keep, removed = [], 0
    for item in coll["items"]:
        hit = (not id_set or item["id"] in id_set) and (where is None or _meta_match(item.get("meta") or {}, where))
        if hit and (id_set or where):
            removed += 1
        else:
            keep.append(item)
    if not removed:
        return 0
    coll["items"] = keep
    save(coll)
    return removed


def bump_hits(name, item_id):
    """命中一次就把 updatedAt 推到当前时间，LRU 淘汰才不会把常用答案挤掉。"""
    coll = load(name)
    for item in coll["items"]:
        if item["id"] == item_id:
            item["hits"] = int(item.get("hits") or 0) + 1
            item["updatedAt"] = int(time.time())
            save(coll)
            return True
    return False


def query(name, vec, top_k=5, min_score=0.0, where=None):
    """全表余弦扫描 + 元数据过滤，返回 ({"score", "item"} 列表, 诊断信息)，分数从高到低。"""
    if not vec:
        return [], {"items": 0, "candidates": 0, "skipped": 0, "filtered": 0}
    coll = load(name)
    scored = []
    skipped = 0
    filtered = 0
    for item in coll["items"]:
        iv = item.get("vec") or []
        if len(iv) != len(vec):
            skipped += 1          # 维度不同说明是旧模型写的，不可比
            continue
        if where and not _meta_match(item.get("meta") or {}, where):
            filtered += 1         # 元数据没过（比如是别的人设存的），也不可比
            continue
        scored.append((cosine(vec, iv), item))
    scored.sort(key=lambda x: -x[0])
    hits = [{"score": round(s, 4), "item": i} for s, i in scored[:max(1, int(top_k))] if s >= min_score]
    return hits, {"items": len(coll["items"]), "candidates": len(scored),
                  "skipped": skipped, "filtered": filtered}


def stats(name):
    coll = load(name)
    path = col_path(name)
    dims = set()
    for item in coll["items"]:
        dims.add(len(item.get("vec") or []))
    return {"name": name, "items": len(coll["items"]), "model": coll.get("model") or "",
            "dim": coll.get("dim") or 0, "distinctDims": sorted(dims),
            "createdAt": coll.get("createdAt") or 0, "updatedAt": coll.get("updatedAt") or 0,
            "bytes": os.path.getsize(path) if os.path.isfile(path) else 0,
            "totalHits": sum(int(i.get("hits") or 0) for i in coll["items"])}


def list_collections():
    if not os.path.isdir(COL_DIR):
        return []
    out = []
    for fname in sorted(os.listdir(COL_DIR)):
        if fname.endswith(".json"):
            out.append(stats(fname[:-5]))
    return out


def cosine(a, b):
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / math.sqrt(na * nb)

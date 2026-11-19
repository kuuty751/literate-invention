# -*- coding: utf-8 -*-
"""
极简 RAG（检索增强生成）。

流程：
  上传文本 → 切片(chunking) → 逐片调 embedding 向量化 → 落盘 kb/<文档id>.json
  提问     → 问题向量化 → 与所有片段算余弦相似度 → 取 top-k → 拼进 system → 交给大模型

存储就用项目一直在用的那套：本地 JSON 文件 + threading.Lock + .tmp 后 os.replace，
不引入 numpy / faiss / 向量数据库，装包只有 fastapi / uvicorn / requests。

  kb/<文档id>.json          文档向量（一份文档一个文件）
  kb/collections/qa.json    问答缓存（走 vstore，支持单条增量写和按条件删）

提问时先拿问题向量去问答缓存里找"是不是问过同样的意思"（cache_lookup），
相似度够高就直接回缓存答案、一次大模型都不调；没命中才检索文档、生成、把问答对写回缓存。
复用还要对历史（context_tag）：在某个上下文里答出来的那条，只在同样的上下文里才拿出来。
"""
import hashlib
import json
import math
import os
import re
import secrets
import threading
import time

import requests

import config
import vstore

ROOT = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.join(ROOT, "kb")

# 文档 id 直接当文件名，所以只允许这一种形状；中文标题存在 name 字段里
ID_RE = re.compile(r"^d\d{14}-[0-9a-f]{4}$")
# 百炼 embedding 一次最多 10 条，超了直接 400
EMBED_BATCH = 10
SOURCES_HEADER = "X-RAG-Sources"
CACHE_HEADER = "X-RAG-Cache"

_lock = threading.Lock()


class RagError(Exception):
    """给 api.py 直接转换成 4xx/5xx 的错误，消息是要展示给学生看的。"""


# ---------------- 切片 ----------------
_HEADING_SPLIT = re.compile(r"\n(?=#{1,6}\s)")
_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;\n])")


def _pack(sentences, size, overlap):
    """按句装到 size 字为止，下一块从上一块结尾带回约 overlap 字，避免句子被切两段。"""
    chunks, cur, length = [], [], 0
    for sent in sentences:
        if len(sent) > size:
            # 长代码块、长表格这类「一句」超过整块预算，只能硬切
            if cur:
                chunks.append("".join(cur).strip())
                cur, length = [], 0
            for i in range(0, len(sent), size):
                chunks.append(sent[i:i + size])
            continue
        if length + len(sent) > size and cur:
            chunks.append("".join(cur).strip())
            keep, acc = [], 0
            for sent_tail in reversed(cur):
                if acc >= overlap:
                    break
                keep.insert(0, sent_tail)
                acc += len(sent_tail)
            cur, length = keep, acc
        cur.append(sent)
        length += len(sent)
    if cur:
        chunks.append("".join(cur).strip())
    return [c for c in chunks if c]


def split_chunks(text, size=None, overlap=None):
    """先按 Markdown 标题切段，段内再按句装箱；跨块时把标题补回去当上下文。"""
    size = size or config.RAG_CHUNK_CHARS
    overlap = overlap or config.RAG_CHUNK_OVERLAP
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text).strip()
    if not text:
        return []
    out = []
    for block in _HEADING_SPLIT.split(text):
        block = block.strip("\n")
        if not block:
            continue
        head = ""
        first = block.split("\n", 1)[0].strip()
        if re.match(r"#{1,6}\s", first):
            head = first
        body = block
        for idx, piece in enumerate(_pack(_SENT_SPLIT.split(body), size, overlap)):
            if idx and head and not piece.lstrip().startswith("#"):
                piece = head + "\n" + piece
            out.append(piece)
    return out


# ---------------- 向量化 ----------------
def embed(texts):
    """调百炼的 OpenAI 兼容 /embeddings。批量上限 10，所以按 10 条一批串行发。"""
    key = (config.API_KEY or "").strip()
    if not key:
        raise RagError("后端未配置 API Key：请编辑 config.py 的 API_KEY 后重启服务")
    url = config.BASE_URL.rstrip("/") + "/embeddings"
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    vectors = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start:start + EMBED_BATCH]
        body = {"model": config.EMBED_MODEL, "input": batch,
                "dimensions": config.EMBED_DIM}
        if config.EMBED_TEXT_TYPE:
            body["text_type"] = config.EMBED_TEXT_TYPE
        try:
            resp = requests.post(url, headers=headers, json=body,
                                 timeout=(10, 120))
        except requests.RequestException as exc:
            raise RagError("无法连接向量服务：%s" % exc)
        if resp.status_code != 200:
            raise RagError("向量化失败 HTTP %s：%s" % (resp.status_code, resp.text[:200]))
        try:
            data = resp.json().get("data") or []
        except ValueError:
            raise RagError("向量服务返回的不是 JSON")
        if len(data) != len(batch):
            raise RagError("向量条数与文本条数不一致")
        # 返回项带 index，按 index 排回来才和输入一一对应
        for item in sorted(data, key=lambda d: d.get("index", 0)):
            vectors.append(item.get("embedding") or [])
    if not vectors or any(len(v) == 0 for v in vectors):
        raise RagError("向量服务返回了空向量，请检查 config.py 的 EMBED_MODEL")
    return vectors


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


# ---------------- 落盘 ----------------
def doc_path(doc_id):
    return os.path.join(KB_DIR, doc_id + ".json")


def _atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def load_doc(doc_id):
    if not ID_RE.match(str(doc_id or "")):
        return None
    path = doc_path(doc_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("chunks"), list):
        return None
    return data


def all_docs():
    """按上传时间倒序返回目录列表（不含向量），供 /api/rag/status 展示。"""
    if not os.path.isdir(KB_DIR):
        return []
    out = []
    for name in sorted(os.listdir(KB_DIR)):
        if not name.endswith(".json"):
            continue
        doc = load_doc(name[:-5])
        if not doc:
            continue
        chunks = [c for c in doc["chunks"] if isinstance(c, dict)]
        out.append({"id": doc.get("id") or name[:-5],
                    "name": doc.get("name") or name[:-5],
                    "chars": doc.get("chars") or 0,
                    "chunks": len(chunks),
                    "model": doc.get("model") or "",
                    "dim": doc.get("dim") or 0,
                    "createdAt": doc.get("createdAt") or 0,
                    "current": (doc.get("model") or "") == config.EMBED_MODEL
                               and (doc.get("dim") or 0) == config.EMBED_DIM})
    out.sort(key=lambda d: -d["createdAt"])
    return out


def add_doc(name, text, replace=True):
    """切片 → 向量化 → 写 kb/<id>.json。replace=True 时同名文档先删掉再写，避免库里堆重复版本。"""
    name = str(name or "").strip()[:120]
    if not name:
        raise RagError("文档名不能为空")
    text = str(text or "")
    if len(text) > config.RAG_MAX_DOC_CHARS:
        raise RagError("文档太长（%d 字，上限 %d 字），请先拆分"
                       % (len(text), config.RAG_MAX_DOC_CHARS))
    pieces = split_chunks(text)
    if not pieces:
        raise RagError("文档没有可用的正文")
    if len(pieces) > config.RAG_MAX_CHUNKS:
        raise RagError("切片过多（%d 片，上限 %d 片），请缩短文档"
                       % (len(pieces), config.RAG_MAX_CHUNKS))
    replaced = []
    if replace:
        for entry in all_docs():
            if entry["name"] == name:
                remove_doc(entry["id"])
                replaced.append(entry["id"])
    started = time.time()
    vectors = embed(pieces)
    doc_id = "d" + time.strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(2)
    doc = {"id": doc_id, "name": name, "model": config.EMBED_MODEL,
           "dim": len(vectors[0]), "createdAt": int(time.time()),
           "chars": len(text.strip()),
           "chunks": [{"i": i, "text": t, "vec": [round(v, 5) for v in vec]}
                      for i, (t, vec) in enumerate(zip(pieces, vectors))]}
    with _lock:
        os.makedirs(KB_DIR, exist_ok=True)
        _atomic_write(doc_path(doc_id), json.dumps(doc, ensure_ascii=False))
    return {"id": doc_id, "name": name, "chars": doc["chars"],
            "chunks": len(pieces), "model": doc["model"], "dim": doc["dim"],
            "createdAt": doc["createdAt"], "seconds": round(time.time() - started, 1),
            "replaced": replaced}


def remove_doc(doc_id):
    if not ID_RE.match(str(doc_id or "")):
        raise RagError("非法的文档 id")
    with _lock:
        if not os.path.isfile(doc_path(doc_id)):
            return False
        os.remove(doc_path(doc_id))
    # 答案是从这份文档检索出来的，文档没了那条缓存就是过期答案
    cache_drop_docs([doc_id])
    return True


# ---------------- 检索 ----------------
def user_text(messages):
    """取最后一条用户消息当检索词。图片理解那种 content 是数组的，只取其中的文字。"""
    for msg in reversed(messages or []):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(str(p.get("text") or "") for p in content
                             if isinstance(p, dict) and p.get("type") == "text")
    return ""


def search(query, top_k=None, min_score=None, doc_ids=None, qvec=None):
    """返回 (命中片段, 诊断信息)。片段里带 1 开始的 rank，注入 prompt 时直接用。

    doc_ids 给了就只在这些文档里检索（向量库常见的 metadata filter）；
    qvec 传入已经算好的问题向量就不再重复调 embedding。
    """
    query = str(query or "").strip()
    top_k = int(top_k or config.RAG_TOP_K)
    min_score = config.RAG_MIN_SCORE if min_score is None else float(min_score)
    want = set(str(d) for d in (doc_ids or []))
    diag = {"query": query[:200], "docs": 0, "chunks": 0, "skipped": 0, "filtered": 0,
            "topK": top_k, "minScore": min_score, "model": config.EMBED_MODEL}
    if want:
        diag["docIds"] = sorted(want)
    if not query:
        raise RagError("检索内容不能为空")
    if qvec is None:
        qvec = embed([query])[0]
    scored = []
    for entry in all_docs():
        diag["docs"] += 1
        if want and entry["id"] not in want:
            diag["filtered"] += entry["chunks"]
            continue
        if not entry["current"]:
            # 向量化模型换了或维度改了，旧文件的向量不可比，只能重新上传
            diag["skipped"] += entry["chunks"]
            continue
        doc = load_doc(entry["id"])
        for chunk in doc["chunks"]:
            vec = chunk.get("vec")
            if not isinstance(vec, list) or len(vec) != entry["dim"]:
                diag["skipped"] += 1
                continue
            diag["chunks"] += 1
            scored.append((cosine(qvec, vec), entry, chunk))
    scored.sort(key=lambda x: -x[0])
    hits = []
    for score, entry, chunk in scored[:top_k]:
        if score < min_score:
            continue
        # 编号在过滤之后才排，避免出现 [资料1] [资料3] 这种跳号
        hits.append({"rank": len(hits) + 1, "doc": entry["id"], "name": entry["name"],
                     "i": chunk.get("i"), "score": round(score, 4),
                     "text": str(chunk.get("text") or "")[:2000]})
    diag["candidates"] = len(scored)
    return hits, diag


def context_block(hits):
    lines = ["[资料%d] 《%s》第 %s 段（相似度 %.3f）\n%s"
             % (h["rank"], h["name"], h["i"], h["score"], h["text"]) for h in hits]
    return (config.RAG_CONTEXT_HEAD + "\n\n" + "\n\n".join(lines)
            + "\n\n" + config.RAG_CONTEXT_TAIL)


def augment(messages, top_k=None, qvec=None, doc_ids=None):
    """检索并把资料拼进第一条 system 消息；没有可用命中时原样返回。"""
    query = user_text(messages)
    hits, diag = search(query, top_k, doc_ids=doc_ids, qvec=qvec)
    info = {"hits": hits, "diag": diag, "query": query}
    if not hits:
        return messages, info
    msgs = [dict(m) if isinstance(m, dict) else m for m in messages]
    block = context_block(hits)
    for i, msg in enumerate(msgs):
        if isinstance(msg, dict) and msg.get("role") == "system":
            msg["content"] = str(msg.get("content") or "").strip() + "\n\n" + block
            break
    else:
        msgs.insert(0, {"role": "system", "content": block})
    return msgs, info


def sources_header(hits):
    """来源列表走响应头回给前端，这样 SSE 的字节流能保持标准 OpenAI 格式。"""
    brief = [{"name": h["name"], "i": h["i"], "score": h["score"]} for h in hits]
    return json.dumps(brief, ensure_ascii=True, separators=(",", ":"))


# ---------------- 问答缓存（语义缓存，存在 vstore 的 qa 集合）----------------
def corpus_tag():
    """语料快照：库里有几份文档、分别是哪几份。只数文件名，不解析内容。

    文档 id 里带着入库时刻（d20261107154002-7e75），所以上传或删除任何一份都会让这个
    串变化，缓存里旧条目的指纹当场对不上。
    """
    try:
        names = sorted(n for n in os.listdir(KB_DIR)
                       if n.endswith(".json") and os.path.isfile(os.path.join(KB_DIR, n)))
    except OSError:
        names = []
    return "%d-%s" % (len(names), hashlib.sha1("|".join(names).encode("utf-8")).hexdigest()[:8])


def fingerprint():
    """影响答案内容的配置快照。指纹变了说明旧缓存不可信，直接不命中。

    末尾那段 lib= 是知识库快照：删文档时引用过它的条目会被连带清掉（cache_drop_docs），
    但**新增**文档没有任何旧条目「引用」它，光靠删除逻辑清不干净——「先问过、后补资料」
    就会回放一条「资料还不存在时」的拒答。把语料并进指纹，补了资料旧答案就一起作废。
    """
    return "%s|%d|k%d|s%.2f|c%d|lib=%s" % (config.EMBED_MODEL, config.EMBED_DIM, config.RAG_TOP_K,
                                           config.RAG_MIN_SCORE, config.RAG_CHUNK_CHARS, corpus_tag())


def scope_of(messages, model="", mode=""):
    """同一套系统提示词 + 同一个对话模型 + 同一种回答模式才算同一个问题域。

    mode 带的是这次请求的开关（有没有拼知识库资料、有没有联网搜索、温度多少）：
    勾知识库时答案里会有「据[资料2]」，不勾时没有，两者不能互相复用，
    否则不勾知识库的一问会把带引用的那条搬过来。角色之间也靠这个隔离。
    """
    parts = []
    for msg in messages or []:
        if isinstance(msg, dict) and msg.get("role") == "system":
            parts.append(str(msg.get("content") or ""))
    raw = ("%s\n%s\n%s" % (model or config.MODEL, mode, "\n".join(parts))).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def context_tag(messages):
    """本次提问之前已经聊过的那几轮，压成一个短串；第一句提问没有历史，返回空串。

    scope 只管人设、模型、模式，管不到「这句话是在聊到什么之后才问出来的」——
    而历史会实打实改变答案：前面刚讨论过 WiFi 密码，接着问「我感冒了有什么建议」，
    温度锁 0 的模型可能顺着老话题把 WiFi 那段又说一遍。这种答案只在当时那个上下文里
    成立，所以要把历史记进缓存条目，换个上下文就别拿出来复用。
    system 不进这里，它已经算进 scope 了。
    """
    turns = [m for m in (messages or [])
             if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
    for i in range(len(turns) - 1, -1, -1):
        if turns[i].get("role") == "user":
            turns = turns[:i]      # 这句就是本次要回答的问题，它之前的才算历史
            break
    if not turns:
        return ""
    raw = "\n".join("%s:%s" % (m.get("role"), m.get("content") or "") for m in turns)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def cache_lookup(qvec, scope, ctx=None):
    """在缓存集合里找"问过同样的意思"。命中返回条目 dict，没命中返回 None。

    ctx 传字符串时按历史过滤；传 None 是不看历史（探测接口只要相似度，不关心上下文）。
    """
    if not config.CACHE_ENABLED or not qvec:
        return None, {"enabled": bool(config.CACHE_ENABLED), "items": 0, "best": None}
    # 阈值自己在下面卡：让 vstore 返回全量最近邻，才能告诉前端"最像的一条只有 0.79、
    # 没到 0.80"，这个数正是用户调阈值要看的。
    hits, diag = vstore.query(config.CACHE_COLLECTION, qvec, top_k=3, where={"scope": scope})
    diag["minScore"] = config.CACHE_MIN_SCORE
    diag["best"] = hits[0]["score"] if hits else None
    for hit in hits:
        if hit["score"] < config.CACHE_MIN_SCORE:
            break
        meta = hit["item"].get("meta") or {}
        if meta.get("fp") != fingerprint():
            diag["stale"] = diag.get("stale", 0) + 1
            continue
        # 空串 = 当时就是第一句提问，答案不依赖任何历史，放到哪个会话里复用都成立；
        # 非空就说明这条是在某段聊天之后答的，只有历史完全一样才敢再拿出来。
        entry_ctx = str(meta.get("ctx") or "")
        if ctx is not None and entry_ctx and entry_ctx != ctx:
            diag["context"] = diag.get("context", 0) + 1
            continue
        ttl = int(config.CACHE_TTL_SECONDS or 0)
        if ttl and int(time.time()) - int(hit["item"].get("updatedAt") or 0) > ttl:
            diag["expired"] = diag.get("expired", 0) + 1
            continue
        # 命中就记一次复用，前端「复用次数」和 totalHits 靠这个数
        vstore.bump_hits(config.CACHE_COLLECTION, hit["item"]["id"])
        return {"id": hit["item"]["id"], "score": hit["score"],
                "question": meta.get("q") or hit["item"].get("text") or "",
                "answer": meta.get("answer") or "", "sources": meta.get("sources") or [],
                "model": meta.get("model") or config.MODEL}, diag
    return None, diag


def cache_store(question, qvec, answer, hits, scope, model="", ctx=""):
    """把这一轮问答存进缓存。答案为空的不存（半截被打断的那种没资格被复用）。

    hits 可以是空列表——不勾知识库的普通对话也走缓存，这时它只是没有引用来源。
    ctx 是 context_tag 算出来的历史串，回放时靠它判断这条换个会话还能不能用。
    """
    if not config.CACHE_ENABLED or not (answer or "").strip():
        return None
    entry_id = "q" + time.strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(2)
    meta = {"q": str(question or "")[:500], "answer": str(answer)[:8000],
            "scope": scope, "ctx": ctx or "", "fp": fingerprint(), "model": model or config.MODEL,
            "sources": [{"name": h["name"], "i": h["i"], "score": h["score"]} for h in hits],
            "docs": sorted({h["doc"] for h in hits}), "ts": int(time.time())}
    vstore.upsert(config.CACHE_COLLECTION,
                  [{"id": entry_id, "text": str(question or "")[:4000], "vec": qvec, "meta": meta}],
                  model=config.EMBED_MODEL, dim=config.EMBED_DIM,
                  max_items=config.CACHE_MAX_ENTRIES)
    return entry_id


def cache_list(limit=50):
    coll = vstore.load(config.CACHE_COLLECTION)
    items = sorted(coll["items"], key=lambda i: -(int(i.get("updatedAt") or 0)))
    out = []
    for item in items[:max(1, int(limit))]:
        meta = item.get("meta") or {}
        out.append({"id": item["id"], "question": meta.get("q") or item.get("text") or "",
                    "answer": str(meta.get("answer") or "")[:160],
                    "hits": int(item.get("hits") or 0),
                    "scope": meta.get("scope") or "",
                    "ctx": meta.get("ctx") or "",
                    "sources": meta.get("sources") or [], "docs": meta.get("docs") or [],
                    "model": meta.get("model") or "",
                    "createdAt": item.get("createdAt"), "updatedAt": item.get("updatedAt"),
                    "current": meta.get("fp") == fingerprint()})
    return out, vstore.stats(config.CACHE_COLLECTION)


def cache_drop_docs(doc_ids):
    """删文档时把引用过它的缓存条目一起清掉，否则下次会秒回一个基于已删资料的答案。"""
    removed = 0
    for doc_id in doc_ids or []:
        try:
            removed += vstore.delete(config.CACHE_COLLECTION, where={"docs": doc_id})
        except vstore.StoreError:
            return removed
    return removed


def cache_clear(ids=None):
    col = config.CACHE_COLLECTION
    if ids:
        return vstore.delete(col, ids=[str(i) for i in ids])
    return vstore.clear(col)


def cache_stats():
    return vstore.stats(config.CACHE_COLLECTION)

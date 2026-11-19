# -*- coding: utf-8 -*-
"""
AI 助手后端（FastAPI）

  1. 托管前端静态页面 —— 浏览器打开 http://127.0.0.1:8000 即可，不必再单开服务器
  2. 登录 / 注册 / 改密码 —— 账号只存加盐哈希，会话走 HttpOnly Cookie
  3. 转发大模型请求 —— API Key 只在服务端拼接，前端与浏览器历史里都不留明文
  4. 文生图 / 图生图 —— 调用百炼 qwen-image 同步接口，结果图代取回本机
  5. 角色提示词 / 历史对话 —— 读写 prompts/*.md 与 history/*.json
  6. MCP 工具调用 —— 对话时可挂本地天气服务，由模型自己决定要不要调
  7. RAG 知识库 —— 上传文档切片向量化存到 kb/*.json，提问时先检索再交给模型
  8. 问答缓存 —— 温度为 0 的角色或勾了知识库的回答存进 kb/collections/qa.json，
     同义改写直接命中缓存，不再调大模型（同一道题每次答案也因此在字面上都一样）

依赖：fastapi / uvicorn / requests（MCP 功能另需 mcp）
运行：python api.py
"""
import base64
import json
import os
import time
from urllib.parse import urlparse

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

import auth
import config
import rag
import store
import vstore

try:
    import mcp_tool
except ImportError:
    # MCP 是可装可不装的扩展（pip install mcp），缺了它其余功能照常跑
    mcp_tool = None

ROOT = os.path.dirname(os.path.abspath(__file__))
TIMEOUT = (10, 300)  # (连接超时, 读取超时) 秒
IMAGE_TIMEOUT = (10, 600)  # 出图是同步等待，给足一分钟以上
COOKIE = "ai_session"

app = FastAPI(title="AI 助手后端")

# 静态目录就是项目根目录，若不加这道拦截，/config.py 会带着明文密钥、
# /users.json 会带着密码哈希被人直接下载。前端不需要任何 .json 静态文件。
BLOCKED = ("__pycache__", ".py", ".log", ".ini", ".json")
# 例外：Swagger（/docs）自己要靠这份 schema 才能在线试接口，里面没有任何密钥
ALLOWED = ("/openapi.json",)


@app.middleware("http")
async def deny_source_download(request, call_next):
    path = request.url.path
    if path not in ALLOWED and (path.endswith(BLOCKED) or
                                any(seg in path for seg in ("__pycache__", "/.", "/api.py", "/config.py"))):
        return PlainTextResponse("Not Found", status_code=404)
    return await call_next(request)


def upstream_url(base_url):
    base = (base_url or config.BASE_URL).strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="baseUrl 必须以 http:// 或 https:// 开头")
    return base + "/chat/completions"


def current_user(request: Request):
    """受保护的接口调用它；未登录直接 401，前端收到后会退回登录页。"""
    username = auth.username_of(request.cookies.get(COOKIE, ""))
    if not username:
        raise HTTPException(status_code=401, detail="请先登录")
    return username


def auth_json(payload, status_code=200, token="", clear=False):
    resp = JSONResponse(payload, status_code=status_code)
    if token:
        resp.set_cookie(COOKIE, token, max_age=auth.SESSION_TTL, httponly=True,
                        samesite="lax", path="/")
    if clear:
        resp.delete_cookie(COOKIE, path="/")
    return resp


def key_tail():
    key = (config.API_KEY or "").strip()
    return key[-4:] if key else ""


@app.post("/api/register")
def register(payload: dict):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    ok, message = auth.register(username, password)
    if not ok:
        return auth_json({"error": message}, status_code=400)
    # 注册成功后直接发会话，省掉「注册完还要再登录一次」的别扭体验
    return auth_json({"ok": True, "username": username}, token=auth.start_session(username))


@app.post("/api/login")
def login(payload: dict):
    username = (payload.get("username") or "").strip()
    ok, result = auth.login(username, payload.get("password") or "")
    if not ok:
        return auth_json({"error": result}, status_code=401)
    return auth_json({"ok": True, "username": username}, token=result)


@app.post("/api/logout")
def logout(request: Request):
    auth.logout(request.cookies.get(COOKIE, ""))
    return auth_json({"ok": True}, clear=True)


@app.get("/api/me")
def me(request: Request):
    username = current_user(request)
    return {"ok": True, "username": username, "hasKey": bool(key_tail()), "keyTail": key_tail(),
            "baseUrl": config.BASE_URL, "model": config.MODEL}


@app.post("/api/password")
def password(request: Request, payload: dict):
    username = current_user(request)
    ok, message = auth.change_password(username, payload.get("oldPassword") or "",
                                       payload.get("newPassword") or "")
    if not ok:
        return auth_json({"error": message}, status_code=400)
    # 改密已让旧 token 失效，这里顺手清掉浏览器里那枚作废的 Cookie
    return auth_json({"ok": True, "relogin": True}, clear=True)


@app.get("/api/health")
def health():
    """前端启动时探测后端是否就绪。Key 末 4 位属于登录后才该看的信息，放在 /api/me。"""
    return {
        "hasKey": bool(key_tail()),
        "model": config.MODEL,
        "imageSizes": config.IMAGE_SIZES,
        "imageModels": config.IMAGE_MODELS,
        "imageModel": config.IMAGE_MODEL,
        "imageMaxCount": config.IMAGE_MAX_COUNT,
        "roles": config.ROLE_IDS,
        "mcp": mcp_tool is not None,
        "rag": {"model": config.EMBED_MODEL, "dim": config.EMBED_DIM,
                "topK": config.RAG_TOP_K, "minScore": config.RAG_MIN_SCORE,
                "chunkChars": config.RAG_CHUNK_CHARS,
                "maxDocChars": config.RAG_MAX_DOC_CHARS,
                "cache": {"enabled": bool(config.CACHE_ENABLED),
                          "minScore": config.CACHE_MIN_SCORE,
                          "maxEntries": config.CACHE_MAX_ENTRIES,
                          "collection": config.CACHE_COLLECTION}},
    }


def check_role(role):
    if role not in config.ROLE_IDS:
        raise HTTPException(status_code=400, detail="未知的角色 id")
    return role


def check_history_role(role):
    """历史对话要能容纳前端自己加的自定义角色，只校验形状，不查白名单。"""
    if not store.safe_key(role):
        raise HTTPException(status_code=400, detail="非法的角色 id")
    return role


@app.get("/api/prompts")
def prompts_read_all(request: Request):
    """读角色提示词 md 文件：一次把所有已自定义的角色设定发给前端。"""
    current_user(request)
    return {"ok": True, "prompts": store.read_all_prompts(config.ROLE_IDS)}


@app.get("/api/prompt")
def prompt_read(request: Request, role: str = Query(..., max_length=40)):
    """读单个角色的 md 文件。exists=False 表示前端该用 config.js 的默认设定。"""
    current_user(request)
    check_role(role)
    text, exists = store.read_prompt(role)
    return {"ok": True, "role": role, "content": text, "exists": exists}


@app.post("/api/prompt")
def prompt_write(request: Request, payload: dict):
    """写角色提示词 md 文件；content 传空串等于删除，即恢复默认。"""
    current_user(request)
    role = check_role(str(payload.get("role") or ""))
    content = str(payload.get("content") or "")
    if len(content) > 20000:
        raise HTTPException(status_code=400, detail="提示词太长（上限 20000 字）")
    if not store.write_prompt(role, content):
        raise HTTPException(status_code=400, detail="写入失败")
    text, exists = store.read_prompt(role)
    return {"ok": True, "role": role, "exists": exists, "chars": len(text)}


@app.get("/api/history")
def history_read(request: Request, role: str = Query(..., max_length=40)):
    """读指定历史对话信息：按「当前用户 + 角色」取回消息列表。"""
    user = current_user(request)
    check_history_role(role)
    return {"ok": True, "role": role, "messages": store.read_history(user, role)}


@app.get("/api/history/all")
def history_read_all(request: Request):
    """登录后一次取回该用户所有角色的历史。目录里有什么就发什么，
    这样前端删掉又重建的自定义角色也不会丢记录。"""
    user = current_user(request)
    path = store.history_path(user)
    convos = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                convos = {k: v for k, v in data.items() if isinstance(v, list) and v}
        except (ValueError, OSError):
            convos = {}
    return {"ok": True, "conversations": convos}


@app.post("/api/history")
def history_write(request: Request, payload: dict):
    """整段覆盖某个角色的历史。前端在每轮对话结束后同步一次。"""
    user = current_user(request)
    role = check_history_role(str(payload.get("role") or ""))
    msgs = payload.get("messages")
    if not isinstance(msgs, list):
        raise HTTPException(status_code=400, detail="messages 必须是数组")
    store.write_history(user, role, msgs)
    return {"ok": True, "role": role, "saved": len(store.read_history(user, role))}


@app.post("/api/history/clear")
def history_clear(request: Request, payload: dict):
    user = current_user(request)
    role = str(payload.get("role") or "all")
    if role != "all":
        check_history_role(role)
    store.clear_history(user, None if role == "all" else role)
    return {"ok": True, "cleared": role}


def chat_with_mcp(base, body, key, extra_headers=None):
    """走 MCP 工具：模型自己决定要不要调 get_weather，所以这一路不做流式输出。"""
    if mcp_tool is None:
        return JSONResponse({"error": "MCP 工具不可用：请先执行 pip install mcp 再重启服务"},
                            status_code=500)
    messages = body.get("messages") or []

    def chat_fn(convo, tools):
        req = dict(body)
        req["messages"] = convo
        req["tools"] = tools
        req.pop("stream", None)
        req.pop("enable_search", None)  # 工具已经给了实时数据，不必再联网搜
        resp = requests.post(upstream_url(base), json=req,
                             headers={"Authorization": "Bearer " + key,
                                      "Content-Type": "application/json"},
                             timeout=TIMEOUT)
        if resp.status_code != 200:
            raise RuntimeError("上游返回 HTTP %s：%s" % (resp.status_code, resp.text[:300]))
        return (resp.json().get("choices") or [{}])[0]

    try:
        result = mcp_tool.run(messages, chat_fn)
    except Exception as exc:
        real = exc.__cause__ or exc
        while getattr(real, "exceptions", None):
            real = real.exceptions[0]
        return JSONResponse({"error": "MCP 工具调用失败：%s" % (str(real)[:300],)}, status_code=502)
    return JSONResponse({"choices": [{"message": {"role": "assistant", "content": result["content"]},
                                      "finish_reason": "stop"}],
                         "mcpCalls": result["calls"]}, headers=extra_headers or {})


def cache_mode(use_rag, body):
    """缓存作用域里的「模式」段：同样的人设和模型，开没开知识库、温度多少，
    答案不该互相复用——勾知识库的答案带「据[资料2]」，没勾的没有。"""
    bits = ["rag"] if use_rag else []
    if body.get("enable_search"):
        bits.append("search")
    return ",".join(bits) + "|t=%s" % body.get("temperature", "")


@app.post("/api/chat")
def chat(request: Request, payload: dict):
    """把前端的 chat/completions 请求原样转发给上游，并把响应透传回去。

    baseUrl / mcp / rag / cache 这四个字段由后端消化，不发给上游；
    temperature 和 seed 原样转发（前端默认温度 0 + 固定 seed，为的是同题同答）。
    """
    current_user(request)
    key = (config.API_KEY or "").strip()
    if not key:
        return JSONResponse({"error": "后端未配置 API Key：请编辑 config.py 的 API_KEY 后重启服务"},
                            status_code=500)

    base = payload.pop("baseUrl", "")
    use_mcp = bool(payload.pop("mcp", False))
    use_rag = bool(payload.pop("rag", False))
    # cache 不传就跟着 rag 走；前端现在会显式传：温度锁在 0 的角色也开缓存
    use_cache = payload.pop("cache", None)
    use_cache = use_rag if use_cache is None else bool(use_cache)
    body = {k: v for k, v in payload.items() if v is not None}
    streaming = bool(body.get("stream"))

    # RAG 检索要在转发给模型之前做完，命中的片段拼进 system，
    # 来源清单走响应头回传，这样流式响应的字节流仍然是标准 OpenAI 格式。
    rag_headers = {}
    cache_ctx = None
    messages = body.get("messages") or []
    query = rag.user_text(messages)
    # MCP 那一路有实时数据，识图取决于具体那张图，缓存了下次就答错，这两样都不参与
    multimodal = any(isinstance(m.get("content"), list) for m in messages if isinstance(m, dict))
    qvec = None
    if (use_cache or use_rag) and query.strip() and not use_mcp and not multimodal:
        # 问题向量只算一次，缓存查询和文档检索共用
        try:
            qvec = rag.embed([query])[0]
        except rag.RagError as exc:
            if use_rag:
                return JSONResponse({"error": str(exc)}, status_code=400)
            use_cache = False   # 只是想用缓存兜底时，向量化失败就照常问模型，不影响回答
    scope = rag.scope_of(messages, body.get("model") or "", cache_mode(use_rag, body))
    ctx = rag.context_tag(messages)
    cacheable = bool(use_cache and qvec)
    if cacheable:
        hit, _cdiag = rag.cache_lookup(qvec, scope, ctx)
        if hit:
            return cached_answer(hit, body, streaming, rag_headers)
        cache_ctx = {"query": query, "qvec": qvec, "scope": scope, "hits": [],
                     "model": body.get("model") or config.MODEL, "ctx": ctx, "enabled": True}

    if use_rag:
        try:
            msgs, info = rag.augment(messages, qvec=qvec)
        except rag.RagError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if info["hits"]:
            body["messages"] = msgs
            rag_headers[rag.SOURCES_HEADER] = rag.sources_header(info["hits"])
            if cache_ctx:
                cache_ctx["hits"] = info["hits"]

    if use_mcp:
        return chat_with_mcp(base, body, key, rag_headers)

    try:
        upstream = requests.post(
            upstream_url(base),
            json=body,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            stream=streaming,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        return JSONResponse({"error": "无法连接上游服务：%s" % exc}, status_code=502)

    if upstream.status_code != 200:
        detail = upstream.text[:500]
        upstream.close()
        return JSONResponse({"error": "上游返回 HTTP %s：%s" % (upstream.status_code, detail)},
                            status_code=upstream.status_code)

    if not streaming:
        data = upstream.content
        upstream.close()
        if cache_ctx and cache_ctx["enabled"]:
            try:
                answer = json.loads(data.decode("utf-8", "ignore"))["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError):
                answer = ""
            remember_answer(cache_ctx, answer)
        return Response(content=data, media_type="application/json", headers=rag_headers)

    collected = []

    def pump():
        try:
            for chunk in upstream.iter_content(chunk_size=1024):
                if chunk:
                    collected.append(chunk)
                    yield chunk
        finally:
            upstream.close()  # 前端点「停止」断开连接时，这里负责关掉上游请求
            # 半截就被打断的回答不缓存，所以 sse_answer 只在看到 [DONE] 时才返回内容
            if cache_ctx and cache_ctx["enabled"]:
                remember_answer(cache_ctx, sse_answer(b"".join(collected)))

    sse_headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    sse_headers.update(rag_headers)
    return StreamingResponse(pump(), media_type="text/event-stream", headers=sse_headers)


def remember_answer(cache_ctx, answer):
    """把这轮"检索到的资料 + 模型的回答"写进问答缓存。失败不影响本次回答。"""
    if not (answer or "").strip():
        return
    try:
        rag.cache_store(cache_ctx["query"], cache_ctx["qvec"], answer,
                        cache_ctx["hits"], cache_ctx["scope"], cache_ctx["model"],
                        cache_ctx.get("ctx") or "")
    except (rag.RagError, vstore.StoreError):
        pass


def sse_answer(blob):
    """从 SSE 字节流里把 delta.content 拼回完整回答；没看到 [DONE] 就当作没答完。"""
    parts = []
    finished = False
    for line in blob.decode("utf-8", "ignore").split("\n"):
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            finished = True
            continue
        try:
            obj = json.loads(data)
        except ValueError:
            continue
        for choice in obj.get("choices") or []:
            piece = (choice.get("delta") or {}).get("content")
            if piece:
                parts.append(str(piece))
    return "".join(parts) if finished and parts else ""


def cached_answer(hit, body, streaming, rag_headers):
    """缓存命中：一次大模型都不调，按 OpenAI 的形状把存好的答案发回去。"""
    created = int(time.time())
    model = hit.get("model") or body.get("model") or config.MODEL
    cid = "chatcmpl-" + hit["id"]
    headers = dict(rag_headers)
    headers[rag.CACHE_HEADER] = json.dumps(
        {"hit": True, "id": hit["id"], "score": hit["score"], "question": hit["question"]},
        ensure_ascii=True, separators=(",", ":"))
    if hit.get("sources"):
        headers[rag.SOURCES_HEADER] = json.dumps(hit["sources"], ensure_ascii=True,
                                                 separators=(",", ":"))
    if not streaming:
        return JSONResponse({
            "model": model, "id": cid, "created": created, "object": "chat.completion",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": hit["answer"]}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "cached": True}, headers=headers)

    base_chunk = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model}

    def emit():
        first = dict(base_chunk)
        first["choices"] = [{"index": 0, "delta": {"role": "assistant", "content": hit["answer"]},
                             "finish_reason": None, "logprobs": None}]
        yield "data: %s\n\n" % json.dumps(first, ensure_ascii=False)
        last = dict(base_chunk)
        last["choices"] = [{"index": 0, "delta": {}, "finish_reason": "stop", "logprobs": None}]
        yield "data: %s\n\n" % json.dumps(last, ensure_ascii=False)
        yield "data: [DONE]\n\n"

    sse_headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    sse_headers.update(headers)
    return StreamingResponse(emit(), media_type="text/event-stream", headers=sse_headers)


def dashscope_headers():
    key = (config.API_KEY or "").strip()
    if not key:
        raise HTTPException(status_code=500,
                            detail="后端未配置 API Key：请编辑 config.py 的 API_KEY 后重启服务")
    return {"Authorization": "Bearer " + key, "Content-Type": "application/json"}


def json_of(resp):
    try:
        return resp.json()
    except ValueError:
        return {}


@app.post("/api/image")
def image(request: Request, payload: dict):
    """
    文生图 / 图生图。qwen-image-2.0 是同步接口：一次请求直接返回结果图地址。
    参考图收 base64 data URL（本机没有公网地址，百炼也支持），所以不需要图床。
    结果图由后端代取成 data URL 再回给前端，避开跨域下载与链接过期两个坑。
    """
    current_user(request)
    kind = (payload.get("kind") or "t2i").strip()
    if kind not in ("t2i", "i2i"):
        raise HTTPException(status_code=400, detail="kind 只能是 t2i 或 i2i")
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="提示词不能为空")
    model = payload.get("model") if payload.get("model") in config.IMAGE_MODELS else config.IMAGE_MODEL
    size = payload.get("size") or config.IMAGE_SIZES[0]
    if size not in config.IMAGE_SIZES:
        raise HTTPException(status_code=400, detail="不支持的尺寸：" + str(size))
    try:
        count = int(payload.get("n") or 1)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="生成张数必须是数字")
    if not 1 <= count <= config.IMAGE_MAX_COUNT:
        raise HTTPException(status_code=400, detail="生成张数只能是 1~%d" % config.IMAGE_MAX_COUNT)

    refs = payload.get("images") or []
    if kind == "i2i":
        if not isinstance(refs, list) or not refs:
            raise HTTPException(status_code=400, detail="请先选择参考图")
        if len(refs) > 3:
            raise HTTPException(status_code=400, detail="参考图最多 3 张")
    if not all(str(x).startswith("data:image/") for x in refs):
        raise HTTPException(status_code=400, detail="参考图必须是 base64 data URL")

    # 同一条 message 里先放参考图、再放文字，就是图生图；只放文字就是文生图
    content = [{"image": r} for r in refs] + [{"text": prompt}]
    params = {"size": size, "n": count, "prompt_extend": True}
    negative = (payload.get("negativePrompt") or "").strip()
    if negative:
        params["negative_prompt"] = negative
    body = {"model": model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": params}

    started = time.time()
    try:
        upstream = requests.post(config.IMAGE_ENDPOINT, headers=dashscope_headers(),
                                 json=body, timeout=IMAGE_TIMEOUT)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="无法连接图片生成服务：%s" % exc)
    data = json_of(upstream)
    if upstream.status_code != 200:
        raise HTTPException(status_code=upstream.status_code,
                            detail=data.get("message") or "图片服务返回 HTTP %s" % upstream.status_code)

    urls = []
    for choice in ((data.get("output") or {}).get("choices") or []):
        for part in ((choice.get("message") or {}).get("content") or []):
            if part.get("image"):
                urls.append(part["image"])
    if not urls:
        raise HTTPException(status_code=502,
                            detail="接口没有返回图片：" + json.dumps(data, ensure_ascii=False)[:300])

    images = []
    for url in urls:
        host = urlparse(url).hostname or ""
        if not host.endswith(".aliyuncs.com"):
            raise HTTPException(status_code=502, detail="结果地址不受信任：" + host)
        try:
            blob = requests.get(url, timeout=IMAGE_TIMEOUT)
        except requests.RequestException as exc:
            raise HTTPException(status_code=502, detail="结果图下载失败：%s" % exc)
        if blob.status_code != 200 or not blob.content:
            raise HTTPException(status_code=502, detail="结果图下载失败，请重试")
        mime = blob.headers.get("Content-Type", "image/png").split(";")[0]
        images.append("data:%s;base64,%s" % (mime, base64.b64encode(blob.content).decode("ascii")))

    return {"ok": True, "images": images, "model": model, "size": size,
            "seconds": round(time.time() - started, 1)}


# ---------------- RAG 知识库 ----------------
@app.get("/api/rag/status")
def rag_status(request: Request):
    """知识库现状：有哪些文档、各切了几片、用的是哪个向量模型、缓存里存了几条。"""
    current_user(request)
    docs = rag.all_docs()
    cache = rag.cache_stats()
    return {"ok": True, "docs": docs,
            "totalChunks": sum(d["chunks"] for d in docs),
            "totalChars": sum(d["chars"] for d in docs),
            "model": config.EMBED_MODEL, "dim": config.EMBED_DIM,
            "topK": config.RAG_TOP_K, "minScore": config.RAG_MIN_SCORE,
            "chunkChars": config.RAG_CHUNK_CHARS,
            "maxDocChars": config.RAG_MAX_DOC_CHARS,
            "outdated": [d["id"] for d in docs if not d["current"]],
            "cache": {"items": cache["items"], "totalHits": cache["totalHits"],
                      "bytes": cache["bytes"], "minScore": config.CACHE_MIN_SCORE,
                      "maxEntries": config.CACHE_MAX_ENTRIES,
                      "enabled": bool(config.CACHE_ENABLED)}}


@app.post("/api/rag/doc")
def rag_doc_add(request: Request, payload: dict):
    """上传一份文本文档：切片 → 逐批向量化 → 写进 kb/<id>.json。

    默认同名覆盖（replace），传 "replace": false 就保留旧的那份、并存成第二份。
    """
    current_user(request)
    replace = payload.get("replace")
    replace = True if replace is None else bool(replace)
    try:
        doc = rag.add_doc(payload.get("name"), payload.get("text"), replace=replace)
    except rag.RagError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "doc": doc}


@app.post("/api/rag/doc/remove")
def rag_doc_remove(request: Request, payload: dict):
    """删掉一份文档，就是把它的向量文件删了，不影响别的文档。引用过它的问答缓存同时作废。"""
    current_user(request)
    doc_id = str(payload.get("id") or "")
    before = rag.cache_stats()["items"]
    try:
        removed = rag.remove_doc(doc_id)
    except rag.RagError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not removed:
        raise HTTPException(status_code=404, detail="没有这个文档，或它已经被删掉了")
    return {"ok": True, "removed": doc_id,
            "cacheDropped": max(0, before - rag.cache_stats()["items"])}


@app.post("/api/rag/search")
def rag_search(request: Request, payload: dict):
    """纯检索调试：只看命中了哪几段、相似度多少，不调大模型、不花 token。"""
    current_user(request)
    try:
        top_k = int(payload.get("topK") or config.RAG_TOP_K)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="topK 必须是数字")
    top_k = max(1, min(10, top_k))
    raw_min = payload.get("minScore")
    try:
        min_score = config.RAG_MIN_SCORE if raw_min is None else float(raw_min)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="minScore 必须是数字")
    doc_ids = payload.get("docIds")
    if doc_ids is not None and not isinstance(doc_ids, list):
        raise HTTPException(status_code=400, detail="docIds 必须是数组")
    started = time.time()
    try:
        hits, diag = rag.search(payload.get("query"), top_k, min_score, doc_ids=doc_ids)
    except rag.RagError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "hits": hits, "diag": diag,
            "seconds": round(time.time() - started, 2)}


@app.get("/api/rag/cache")
def rag_cache_list(request: Request, limit: int = Query(50, ge=1, le=200)):
    """问答缓存列表：存了哪些问题、被复用几次、引用了哪几份文档。"""
    current_user(request)
    items, stat = rag.cache_list(limit)
    return {"ok": True, "items": items, "stats": stat,
            "minScore": config.CACHE_MIN_SCORE, "maxEntries": config.CACHE_MAX_ENTRIES,
            "enabled": bool(config.CACHE_ENABLED), "ttl": config.CACHE_TTL_SECONDS,
            "collection": config.CACHE_COLLECTION}


@app.post("/api/rag/cache/lookup")
def rag_cache_lookup(request: Request, payload: dict):
    """只看这个问题会不会命中缓存、相似度多少，不生成、也不新增条目。

    注意命中时照样会记一次复用（hits +1、updatedAt 推到当前），和真实回放同一个计数，
    所以别把它当无副作用的 dry-run。

    除 query 外可带 messages / model / rag / temperature：作用域要和真实问答那条路算得一样，
    否则探测说会命中、真问却不命中。
    探测这一路不看历史（cache_lookup 的 ctx 留 None），它只回答相似度够不够；真实问答还要
    历史对得上，所以「在某段聊天之后答出来的」那几条探测会报命中、真问却不复用。
    """
    current_user(request)
    query = str(payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="检索内容不能为空")
    # 模式段要和 /api/chat 算法一致，否则探测出来的作用域和真正问答对不上
    mode = cache_mode(bool(payload.get("rag")), payload)
    scope = rag.scope_of(payload.get("messages") or [], payload.get("model") or config.MODEL, mode)
    started = time.time()
    try:
        qvec = rag.embed([query])[0]
    except rag.RagError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    hit, diag = rag.cache_lookup(qvec, scope)
    return {"ok": True, "hit": bool(hit), "score": (hit or {}).get("score"),
            "question": (hit or {}).get("question"), "answer": (hit or {}).get("answer"),
            "scope": scope, "diag": diag, "seconds": round(time.time() - started, 2)}


@app.post("/api/rag/cache/clear")
def rag_cache_clear(request: Request, payload: dict):
    """清空问答缓存，或只删指定的几条。文档删了会自动失效对应的条目，这里用于手动兜底。"""
    current_user(request)
    ids = payload.get("ids")
    if ids is not None and not isinstance(ids, list):
        raise HTTPException(status_code=400, detail="ids 必须是数组")
    try:
        removed = rag.cache_clear(ids or None)
    except vstore.StoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "removed": removed, "stats": rag.cache_stats()}


# 静态资源一律 no-cache（内容没变时浏览器拿 304，不费流量）。少了这个头，浏览器会按
# 启发式把 js/css 缓存住，改完代码刷新还是旧页面——这就是「改了没效果」的真正原因。
@app.middleware("http")
async def no_cache_static(request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith(("/api/", "/openapi.json", "/docs", "/redoc")):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/", StaticFiles(directory=ROOT, html=True), name="static")


if __name__ == "__main__":
    print("AI 助手 -> http://%s:%d" % (config.HOST, config.PORT))
    if not (config.API_KEY or "").strip():
        print("提示：config.py 里的 API_KEY 还是空的，对话功能不可用")
    uvicorn.run(app, host=config.HOST, port=config.PORT)

# -*- coding: utf-8 -*-
"""
飞书机器人接入层（可选功能，需要 pip install lark-oapi）。

链路：飞书消息 →（WebSocket 长连接）→ 本文件 → 调本机 api.py 的 /api/chat → 回发原会话。
api.py 一行没改：bot 拿演示账号走 /api/login 拿到和浏览器同一条路的会话 cookie。

跑法（两个终端）：
    python api.py                              终端 1，先起后端
    python feishu_bot.py                       终端 2，起长连接
    python feishu_bot.py --selftest 阈值默认是多少    不连飞书，只验后端这一段

飞书后台要做四件事（少一件就是「已读不回」）：
    1. 自建应用 + 勾选「机器人」能力
    2. 权限：im:message.p2p_msg:readonly、im:message.group_at_msg:readonly、im:message:send_as_bot
    3. 事件与回调 → 订阅方式选「使用长连接接收事件」→ 添加事件 im.message.receive_v1
    4. 创建版本并**发布**——不发布，前三步的权限和事件都不会生效

为什么用长连接而不是回调 URL：回调要公网 HTTPS + 域名 + 证书，而本项目 HOST 故意是 127.0.0.1
（见 config.py 的注释）；长连接是 bot 主动连飞书，只要能出网就行。
"""

import json
import re
import sys
import threading
import time

import requests

import config

API = "http://127.0.0.1:%d" % config.PORT
SEED = 20261104              # 和 js/config.js 里那个固定 seed 保持一致
MAX_REPLY_CHARS = 3000       # 飞书单条文本的长度余量，超了截断
DEDUP_SECONDS = 120          # 同一条飞书消息在这个窗口内只处理一次

# 模式 → 往 /api/chat 里多带的字段。这四样照 js/app.js 拼 body 的那几行抄：
# 温度锁 0、固定 seed、显式 cache=true。cache 必须显式传——不传的话后端只跟着
# rag 走（api.py 里 use_cache = use_rag if None），普通对话那一路就不查缓存了。
BASE_FLAGS = {"temperature": 0, "seed": SEED, "cache": True}
MODES = {
    "rag": {"rag": True},
    "plain": {},
    "search": {"enable_search": True},
    "mcp": {"mcp": True},      # 这路有实时数据，后端本来就跳过缓存
}
COMMANDS = {
    "/rag": ("rag", "已切到知识库问答（会自动查问答缓存）"),
    "/知识库": ("rag", "已切到知识库问答（会自动查问答缓存）"),
    "/plain": ("plain", "已切到普通对话"),
    "/普通": ("plain", "已切到普通对话"),
    "/search": ("search", "已切到联网搜索，这路比较慢"),
    "/搜索": ("search", "已切到联网搜索，这路比较慢"),
    "/weather": ("mcp", "已切到 MCP 天气，直接问「北京天气」这种"),
    "/天气": ("mcp", "已切到 MCP 天气，直接问「北京天气」这种"),
}
MENTION_RE = re.compile(r"@_user_\d+|@_all")

_http = requests.Session()
_lock = threading.Lock()
_states = {}      # chat_id -> {"mode": str, "messages": [...]}
_seen = {}        # 飞书 message_id -> 处理时间，用来挡住长连接重投
_client = None
_REPLY_REQ = None      # 下面两个在 main() 里延迟导入，没装 SDK 时 --selftest 照样能跑
_REPLY_BODY = None


class BotError(Exception):
    pass


def _state(chat_id):
    with _lock:
        return _states.setdefault(chat_id, {"mode": "rag", "messages": []})


def login():
    """用演示账号登录本机后端。会话 token 只存内存，所以后端每次重启都要重新来一次。"""
    if not config.FEISHU_BACKEND_PASSWORD:
        raise BotError("先在 config.py 填 FEISHU_BACKEND_PASSWORD（演示账号的密码）")
    try:
        r = _http.post(API + "/api/login",
                       json={"username": config.FEISHU_BACKEND_USER,
                             "password": config.FEISHU_BACKEND_PASSWORD},
                       timeout=10)
    except requests.RequestException:
        raise BotError("连不上本机后端（%s），先 python api.py 把服务起起来" % API)
    if r.status_code != 200:
        raise BotError("登录本机后端失败 %s：%s" % (r.status_code, _detail(r)))
    return True


def _detail(resp):
    try:
        return str(resp.json().get("detail") or resp.json().get("error") or resp.text[:120])
    except ValueError:
        return resp.text[:120]


def ask(text, state):
    """把这句话连同本会话的历史发给后端，返回（答案, 一行来源注脚）。

    这里不带 system 人设，所以作用域桶和浏览器里选角色的那一路不同（scope =
    sha1(模型 + 模式 + 所有 system 文本)），飞书里问同样的话不会复用页面上存的
    答案——各自内部一致，不是 bug。
    """
    messages = list(state["messages"]) + [{"role": "user", "content": text}]
    body = {"model": config.MODEL, "baseUrl": config.BASE_URL, "messages": messages}
    body.update(BASE_FLAGS)
    body.update(MODES[state["mode"]])
    for attempt in (1, 2):
        try:
            r = _http.post(API + "/api/chat", json=body, timeout=180)
        except requests.RequestException as exc:
            raise BotError("连不上本机后端（%s），确认 api.py 在跑" % type(exc).__name__)
        if r.status_code == 401 and attempt == 1:
            login()
            continue
        break
    if r.status_code != 200:
        raise BotError("后端返回 %s：%s" % (r.status_code, _detail(r)))
    try:
        answer = r.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError):
        raise BotError("后端返回的结构不是标准 OpenAI 形状")
    if not (answer or "").strip():
        raise BotError("模型给了空答案，换种问法再试")

    note = []
    cached = _header_json(r, "x-rag-cache")
    if cached and cached.get("hit"):
        note.append("缓存命中 %s · 0 token" % round(float(cached.get("score") or 0), 4))
        if cached.get("question") and cached["question"] != text:
            note.append("复用的是「%s」" % str(cached["question"])[:24])
    sources = _header_json(r, "x-rag-sources")
    if sources:
        note.append("引用 %d 段：%s" % (len(sources), "、".join("%s#%s" % (s["name"], s["i"]) for s in sources[:4])))
    return answer, " · ".join(note)


def _header_json(resp, name):
    raw = resp.headers.get(name)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _remember(state, text, answer):
    turns = max(0, int(config.FEISHU_CONTEXT_TURNS))
    state["messages"] = (state["messages"] + [{"role": "user", "content": text},
                                              {"role": "assistant", "content": answer}])[-turns * 2:]


def handle(chat_id, message_id, text):
    """一句飞书消息 → 回一句。返回要发回去的文本。"""
    if message_id:
        now = time.time()
        with _lock:
            for mid in [m for m, t in _seen.items() if now - t > DEDUP_SECONDS]:
                _seen.pop(mid, None)
            if message_id in _seen:
                return None      # 长连接重投，这条已经答过了
            _seen[message_id] = now

    state = _state(chat_id)
    cmd = text.strip().lower()
    if cmd in ("/help", "/帮助"):
        return HELP.replace("{mode}", state["mode"])
    if cmd in ("/clear", "/清空"):
        state["messages"] = []
        return "已清空这个会话的上下文（问答缓存不受影响，那是全局的）"
    if cmd in COMMANDS:
        state["mode"], msg = COMMANDS[cmd]
        return msg + "，当前模式：" + state["mode"]

    answer, note = ask(text, state)
    _remember(state, text, answer)
    body = answer if len(answer) <= MAX_REPLY_CHARS else answer[:MAX_REPLY_CHARS] + "\n…（答案过长已截断）"
    return body + ("\n\n— " + note if note else "")


HELP = (
    "这个机器人把本机那个大模型课程项目接到了飞书，后端一行没改，走的还是 /api/chat。\n"
    "当前模式：{mode}\n"
    "可用命令：\n"
    "/rag 知识库问答（默认，本地 kb 检索 + 语义缓存）\n"
    "/plain 普通对话\n"
    "/search 联网搜索\n"
    "/weather MCP 天气工具\n"
    "/clear 清空本会话上下文\n/help 看这段\n\n"
    "演示亮点：先用 /rag 问「文档片段的检索相似度门槛默认是多少？」，注脚会写引用了几段；"
    "再换个说法问「知识库检索的相似度阈值默认是多少？」，注脚会变成「缓存命中 …、0 token」，"
    "这就是语义缓存。别拿耗时判断命中没命中，向量化偶尔会抖到十几秒。"
)

# ---------------- 飞书侧 ----------------


def extract_text(message):
    """飞书的 content 是 JSON 字符串；只处理文字，其它类型（富文本/图片）明说暂不支持。

    字段名有个坑：事件里叫 message_type（发请求时叫 msg_type），抄反了就 AttributeError。
    """
    mtype = getattr(message, "message_type", None)
    if mtype != "text":
        return None, "现在只收文字消息，这条是 %s" % mtype
    try:
        text = json.loads(message.content).get("text", "")
    except (TypeError, ValueError):
        return None, "消息内容解析失败"
    text = MENTION_RE.sub("", str(text)).strip()
    if not text:
        return None, "只看到 @，没看到问题"
    return text, None


def on_message(event):
    message = event.event.message
    text, err = extract_text(message)
    try:
        reply_id = message.message_id
        if err:
            reply(reply_id, err)
            return
        out = handle(message.chat_id, reply_id, text)
        if out:
            reply(reply_id, out)
    except BotError as exc:
        reply_safe(message.message_id, "出错了：" + str(exc))
    except Exception as exc:
        reply_safe(message.message_id, "没处理成功：%s: %s" % (type(exc).__name__, exc))


def reply(message_id, text):
    body = _REPLY_BODY.builder().msg_type("text").content(
        json.dumps({"text": text}, ensure_ascii=False)).build()
    req = _REPLY_REQ.builder().message_id(message_id).request_body(body).build()
    resp = _client.im.v1.message.reply(req)
    if not resp.success():
        raise BotError("回复发送失败 %s：%s" % (resp.code, resp.msg))


def reply_safe(message_id, text):
    try:
        reply(message_id, text)
    except Exception:
        print("连回错误提示都没发出去，看下面的原始异常", file=sys.stderr)
        print(text, file=sys.stderr)


def selftest(text):
    print("后端地址：%s  账号：%s" % (API, config.FEISHU_BACKEND_USER))
    login()
    state = _state("selftest")
    answer, note = ask(text, state)
    _remember(state, text, answer)
    print("答案：%s" % answer)
    print("注脚：%s" % (note or "（没有缓存/引用信息）"))
    again, note2 = ask(text, state)
    print("\n同一句再问一次（期望这次是缓存回放）：%s" % (note2 or "没命中，检查温度/缓存开关"))
    print("两次文本完全相同：%s" % (again == answer))
    return 0


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--selftest":
        try:
            return selftest(" ".join(argv[1:]) or "文档片段的检索相似度门槛默认是多少？")
        except BotError as exc:
            print(exc, file=sys.stderr)
            return 1

    global _client, _REPLY_REQ, _REPLY_BODY
    try:
        import lark_oapi as lark
        from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody
    except ImportError:
        print("没装 lark-oapi：pip install lark-oapi\n"
              "（装不上也不影响本机其它功能，这个文件只是可选的接入层；"
              "想先验后端那一段就 python feishu_bot.py --selftest）")
        return 1
    _REPLY_REQ, _REPLY_BODY = ReplyMessageRequest, ReplyMessageRequestBody
    if not (config.FEISHU_APP_ID and config.FEISHU_APP_SECRET):
        print("先在 config.py 填 FEISHU_APP_ID / FEISHU_APP_SECRET（飞书开放平台「凭证与基础信息」）")
        return 1

    try:
        login()
        print("已登录本机后端")
    except BotError as exc:
        print(exc, file=sys.stderr)
        return 1

    handler = (lark.EventDispatcherHandler
               .builder(config.FEISHU_ENCRYPT_KEY, config.FEISHU_VERIFY_TOKEN)
               .register_p2_im_message_receive_v1(on_message)
               .build())
    _client = lark.Client.builder().app_id(config.FEISHU_APP_ID).app_secret(config.FEISHU_APP_SECRET).build()
    ws = lark.ws.Client(config.FEISHU_APP_ID, config.FEISHU_APP_SECRET, event_handler=handler,
                        log_level=lark.LogLevel.INFO)
    print("长连接启动中。飞书后台记得选「使用长连接接收事件」并添加 im.message.receive_v1，"
          "然后把机器人拉进会话或设为测试人员。Ctrl+C 退出。")
    ws.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())

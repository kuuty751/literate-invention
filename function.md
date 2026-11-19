# 接口文档 function.md

本项目由一个 FastAPI 后端（`api.py`）同时托管前端页面和全部接口。
浏览器访问 `http://127.0.0.1:8000` 即可，接口地址一律是同源相对路径。

## 1. 通用约定

| 项目 | 约定 |
| --- | --- |
| 协议 | HTTP/1.1，全部走 `127.0.0.1:8000` |
| 请求体 | `Content-Type: application/json`，UTF-8 编码 |
| 响应体 | 全部为 JSON 对象（唯一的例外是流式对话，见 5.2，它是 `text/event-stream`） |
| 鉴权 | 登录后服务端下发 `HttpOnly` Cookie `ai_session`；除 `/api/health`、`/api/register`、`/api/login` 外的接口都必须带上它 |
| 未登录 | 返回 `401 {"detail": "请先登录"}`，前端收到后自动退回登录页 |
| 参数错误 | `400 {"detail": "中文说明"}` |
| 业务失败 | 部分接口用 `200/400/401 + {"error": "中文说明"}` 返回，方便前端直接展示这句话 |
| 上游异常 | `502 {"error": "无法连接上游服务：…"}`；Key 未配置为 `500` |
| API Key | 只存在服务端 `config.py`，任何响应里最多出现末 4 位 |
| 知识库引用 | 对话请求带 `"rag": true` 时，响应头 `X-RAG-Sources` 里是一段 JSON 数组字符串，见 5.5 |
| 缓存命中 | 对话请求带 `"cache": true`（温度 0 的角色或勾了知识库时前端会传）且复用了缓存答案，另有响应头 `X-RAG-Cache`，见 5.6 |

`Set-Cookie` 示例（登录成功后）：

```http
Set-Cookie: ai_session=<32 字节随机 token>; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800
```

会话有效期 7 天，每次访问自动续期；修改密码会让该账号已有的会话全部失效。

---

## 2. 账号接口

### 2.1 注册 `POST /api/register`

请求：

```json
{
  "username": "zhangsan",
  "password": "Abc-123456"
}
```

响应 `200`（同时下发会话 Cookie，注册完不用二次登录）：

```json
{ "ok": true, "username": "zhangsan" }
```

失败 `400`：

```json
{ "error": "该用户名已被占用" }
```

用户名规则：中文、字母、数字、下划线、短横线，2~32 位；密码不少于 6 位。
密码在 `users.json` 里只存 `PBKDF2-SHA256`（12 万次迭代 + 每用户独立盐），不存明文。

### 2.2 登录 `POST /api/login`

请求：

```json
{ "username": "zhangsan", "password": "Abc-123456" }
```

响应 `200`：

```json
{ "ok": true, "username": "zhangsan" }
```

失败 `401`：

```json
{ "error": "用户名或密码错误" }
```

### 2.3 退出登录 `POST /api/logout`

请求体为空对象 `{}`。

响应 `200`（同时清除 Cookie）：

```json
{ "ok": true }
```

### 2.4 当前登录信息 `GET /api/me`

响应 `200`：

```json
{
  "ok": true,
  "username": "mcp_ui_test",
  "hasKey": true,
  "keyTail": "zGZj",
  "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "model": "qwen-plus"
}
```

### 2.5 修改密码 `POST /api/password`

请求：

```json
{ "oldPassword": "Abc-123456", "newPassword": "New-888888" }
```

响应 `200`（旧会话全部作废，前端据此跳回登录页）：

```json
{ "ok": true, "relogin": true }
```

失败 `400`：

```json
{ "error": "原密码不正确" }
```

---

## 3. 服务状态 `GET /api/health`

不需要登录，前端启动时用它判断后端是否就绪、能开哪些功能。

响应 `200`（真实抓包）：

```json
{
  "hasKey": true,
  "model": "qwen-plus",
  "imageSizes": ["1024*1024", "1280*1280", "1328*1328", "1664*928", "928*1664", "1280*720", "720*1280"],
  "imageModels": ["qwen-image-2.0", "qwen-image-2.0-pro"],
  "imageModel": "qwen-image-2.0",
  "imageMaxCount": 4,
  "roles": ["normal", "teacher", "doctor", "dream", "name", "elysia", "kb"],
  "mcp": true,
  "rag": {
    "model": "text-embedding-v3",
    "dim": 1024,
    "topK": 4,
    "minScore": 0.45,
    "chunkChars": 500,
    "maxDocChars": 80000,
    "cache": { "enabled": true, "minScore": 0.8, "maxEntries": 200, "collection": "qa" }
  }
}
```

`mcp: false` 表示后端没装 `mcp` 依赖，前端会把「MCP 天气」开关隐藏掉。
`rag` 字段存在表示知识库检索可用，前端才会显示「知识库问答」开关和资料管理页；里面的值就是当前生效的调参结果。
`rag.cache` 是问答缓存的参数，见 5.6。

---

## 4. 角色提示词 md 文件

提示词落在项目目录 `prompts/<角色 id>.md`。**文件存在 = 已自定义，不存在 = 用 `js/config.js` 里的默认设定。**
角色 id 必须在 `config.ROLE_IDS` 白名单内，否则 `400 未知的角色 id`。

一个和「同题同答」直接相关的行为：`config.js` 里那几段默认设定不只是人设，还带着**输出契约**
（选择题第一行「答案：<字母> ｜ 该选项去掉字母后的原文」、简答题【结论】【要点】【易错】那种，见 README 第六节）。
一旦写了 `prompts/teacher.md` 覆盖，契约就跟着人设一起换掉了——温度 0 仍锁得住「选哪个」，
但排版不再有那三行硬约束；同时 system 文本变了，作用域哈希换桶，旧缓存自动不再复用（原理见 5.6）。
删掉 md 恢复默认后，又回到原来那个桶，旧答案还能被捡到。

### 4.1 读全部 `GET /api/prompts`

只返回已经自定义过的角色，一次取回，登录后调用。

```json
{ "ok": true, "prompts": { "teacher": "你是一位大模型应用开发课的老师……" } }
```

### 4.2 读单个 `GET /api/prompt?role=teacher`

```json
{ "ok": true, "role": "teacher", "content": "你是一位大模型应用开发课的老师……", "exists": true }
```

没自定义过时 `exists` 为 `false`，`content` 是空串，前端改用默认设定：

```json
{ "ok": true, "role": "doctor", "content": "", "exists": false }
```

### 4.3 写 / 删除 `POST /api/prompt`

请求（`content` 传空串就是删除这个 md，即恢复默认）：

```json
{ "role": "teacher", "content": "你是一位大模型应用开发课的老师，回答要给出可运行的代码。" }
```

响应 `200`：

```json
{ "ok": true, "role": "teacher", "exists": true, "chars": 33 }
```

删除后：

```json
{ "ok": true, "role": "teacher", "exists": false, "chars": 0 }
```

上限 20000 字，超出返回 `400 {"detail": "提示词太长（上限 20000 字）"}`。
写入是原子的（先写 `.tmp` 再 `os.replace`），并且用一把进程锁串行化，避免并发写坏文件。

---

## 5. AI 对话 `POST /api/chat`

请求体就是 OpenAI 兼容的 `chat/completions` 参数，后端原样转发给百炼，再透传回来。
额外的 `baseUrl` / `mcp` / `rag` / `cache` 四个字段由后端消化，不会发给上游。
`temperature` 和 `seed` 是原样转发的普通字段：前端默认下发 `temperature: 0` + 固定 `seed`，
为的是同一道题每次给同一个结论（角色可以自带温度，见 README 第六节）。
**注意：温度 0 只锁得住「选哪个」，锁不住逐字**——实测关掉缓存连问三次，三份文本两两不同。
字面一模一样由 `cache` 那层保证，见 5.6。

### 5.1 普通对话（非流式）

请求（普通对话角色没有预设人设，这里发的是配置页里那句短设定；内置老师人设是 724 字的锁死输出契约，完整请求见 5.6）：

```json
{
  "model": "qwen-plus",
  "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "temperature": 0,
  "seed": 20261104,
  "cache": true,
  "messages": [
    { "role": "system", "content": "你是一位大模型应用开发课的老师……" },
    { "role": "user", "content": "1+1等于几？只回答数字" }
  ]
}
```

响应 `200`（上游原样返回，真实抓包，1.09 秒）：

```json
{
  "model": "qwen-plus",
  "id": "chatcmpl-70e40e24-bbf3-9be0-a4d4-fb5140b8802b",
  "choices": [
    { "message": { "content": "2", "role": "assistant" }, "index": 0, "finish_reason": "stop" }
  ],
  "created": 1793770784,
  "object": "chat.completion",
  "usage": { "total_tokens": 33, "completion_tokens": 1, "prompt_tokens": 32,
             "prompt_tokens_details": { "cached_tokens": 0 } }
}
```

这条没有 `X-RAG-Cache` 响应头：库里还没有这一问的缓存，所以是现生成的，生成完才会写进去（见 5.6）。
它的作用域是 `3e73574993024084`——和老师人设的 `1dbd901c70b2c9fa` 不是一个桶，所以两者互不复用。

### 5.2 流式对话

请求加 `"stream": true`，响应 `Content-Type: text/event-stream`，分片是标准 OpenAI 形状（真实抓包，问「2+2等于几？只回答数字」）：

```text
data: {"model":"qwen-plus","id":"chatcmpl-f9d24f23-81e7-9906-a9b3-47cec1ded9ec","created":1793769615,"object":"chat.completion.chunk","usage":null,"choices":[{"logprobs":null,"index":0,"delta":{"content":"","role":"assistant"},"finish_reason":null}]}

data: {"model":"qwen-plus","id":"chatcmpl-f9d24f23-81e7-9906-a9b3-47cec1ded9ec","choices":[{"delta":{"content":"4"},"index":0,"finish_reason":null,"logprobs":null}],"created":1793769615,"object":"chat.completion.chunk","usage":null}

data: {"model":"qwen-plus","…","choices":[{"delta":{"content":""},"index":0,"finish_reason":"stop","logprobs":null}]}

data: [DONE]
```

前端逐块拼接渲染，中途点「停止」会中断读取并保留已经生成的部分。
除这一种情况外，全站响应都是 JSON。

### 5.3 联网搜索

请求加一个字段即可（百炼 compatible-mode 原生支持）：

```json
{ "model": "qwen-plus", "messages": [ … ], "enable_search": true }
```

响应结构同 5.1。勾了「MCP 天气」时不会再带这个字段，因为工具已经提供了实时数据。

### 5.4 MCP 工具调用 `"mcp": true`

请求：

```json
{
  "model": "qwen-plus",
  "temperature": 0.2,
  "messages": [
    { "role": "system", "content": "你是一位大模型应用开发课的老师……" },
    { "role": "user", "content": "杭州今天天气怎么样？给出现在的气温和今天的最高最低气温。" }
  ],
  "mcp": true
}
```

后端会拉起本地 MCP 服务 `mcp_server.py`（工具 `get_weather`），把工具描述塞给模型，
模型回 `tool_calls` 后代执行、以 `role: tool` 回填，再问一次拿到最终回答。
这一路是多轮的，所以服务端强制非流式，返回普通 JSON：

```json
{
  "choices": [
    { "message": { "role": "assistant", "content": "杭州今天为阵雨（中），当前气温 22.4°C，最高 22.4°C，最低 15.3°C。" },
      "finish_reason": "stop" }
  ],
  "mcpCalls": [ { "name": "get_weather", "args": { "city": "杭州", "days": 1 } } ]
}
```

`mcpCalls` 可能为空数组——模型判断这个问题不需要查天气时就不会调工具。
最多 4 轮工具调用，超过会中止。工具本身取自 Open-Meteo（免费、无需 Key）。

失败 `502`：

```json
{ "error": "MCP 工具调用失败：上游返回 HTTP 400：…" }
```

### 5.5 知识库问答（RAG）`"rag": true`

请求体不用改结构，多一个 `rag` 字段即可。后端拿最后一条 `user` 消息去本地知识库检索
（接口见第 8 节），把命中的片段拼到第一条 `system` 消息末尾，再转发给上游。

请求（真实抓包。这一组是早先库里装着三份课程资料时抓的，用来展示「多份文档一起排序」；
交付库里是 README.md 加一份 21 字的 `ceshi1.md`，当前状态的报文见 8.1，检索排序的实测见 8.4）：

```json
{
  "model": "qwen-plus",
  "temperature": 0.2,
  "rag": true,
  "messages": [
    { "role": "system", "content": "你是知识库问答助手。" },
    { "role": "user", "content": "我的提交编号是多少？" }
  ]
}
```

响应 `200`，正文是标准 OpenAI 结构：

```json
{
  "choices": [
    { "message": { "role": "assistant",
      "content": "你的提交编号是 **AICHAT-2026-1147**。\n\n据[资料1]，该编号明确记载于《RAG演示资料.md》中，且说明“这串编号只出现在这份文档里，模型不可能凭常识答对”，因此这是唯一权威来源。" } }
  ]
}
```

同一次响应的**响应头**里带回引用了哪几段：

```http
X-RAG-Sources: [{"name":"RAG\u6f14\u793a\u8d44\u6599.md","i":0,"score":0.6897},{"name":"\u7b2c2\u7ae0-\u5411\u91cf\u6570\u636e\u5e93\u4e0eRAG.md","i":0,"score":0.5954},{"name":"RAG\u6f14\u793a\u8d44\u6599.md","i":2,"score":0.5214},{"name":"GBK\u8bfe\u4ef6-\u63d0\u793a\u8bcd\u5de5\u7a0b.txt","i":0,"score":0.5161}]
```

引用走响应头而不是塞进 body，是为了让流式（`text/event-stream`）的分片字节保持标准 OpenAI 格式——
前端逐块拼接时不用特殊处理，只要在 `fetch` 拿到响应后读一次头。所以 `"stream": true` + `"rag": true` 也能拿到引用。
前端把这段解析后存进历史消息的 `rag` 字段（见 7.3），气泡右上角显示「知识库 4 段」，鼠标悬停能看文件名和相似度。

上游实际收到的 `system` 内容是这样拼的（`config.py` 的 `RAG_CONTEXT_HEAD` / `RAG_CONTEXT_TAIL` 可改）：

```text
【本地知识库资料】下面是从你本机 kb 目录里检索出来的片段，按相关度排序。回答必须以这些资料为依据，并在引用处标出编号，例如「据[资料2]」。

[资料1] 《RAG演示资料.md》第 0 段（相似度 0.696）
# RAG 演示资料

本次演示的提交编号是 AICHAT-2026-1147。这串编号只出现在这份文档里，模型不可能凭常识答对。

[资料2] 《第2章-向量数据库与RAG.md》第 0 段（相似度 0.594）
…

规则：1) 资料里没有的内容不要编；2) 资料不足时明确说明缺哪部分，可以补充常识但要标注「以下为通用知识」；3) 中文回答，术语保留原文。
```

对照实验：同样的 `messages` 去掉 `rag` 字段，模型答“我无法获取或查询您的提交编号…”，且响应头里没有 `X-RAG-Sources`。
这组对比说明答案是检索出来的，不是模型凭常识编的——编号只存在于上传的那份文档里。

其它行为：
- 知识库为空、或最高相似度没过阈值时，`messages` 原样转发，响应头是空的，等于没开 RAG。
- `"rag"` 和 `"mcp"` 可以同时为 `true`：先做知识库注入，再走工具调用多轮。
- 勾了知识库或 MCP 时前端不再发 `enable_search`，三个来源只留一个。
- 检索本身出错（比如没配 Key、向量模型不可用）返回 `400 {"error": "中文说明"}`。

### 5.6 问答缓存（温度 0 的角色和勾了知识库的对话，第二道加速）

前端多下发一个 `cache` 字段：**温度为 0 的角色，或者勾了「知识库问答」，就传 `true`**
（创意角色温度 0.8~0.9 传 `false`，因为那三个要的就是每次换个答案）。不传时后端按 `rag` 处理，保持老调用方能用。
总开关是 `config.py` 的 `CACHE_ENABLED = True`。
流程是：把用户那句话向量化**一次**，这个向量先拿去 `kb/collections/qa.json` 里找最像的旧问题，
够像就直接把存好的答案发回去（一次大模型都不调）；不够像才照常走检索 + 生成，生成完再把这轮问答写回缓存。

**未命中**（`POST /api/chat`，真实抓包，5.12 秒，响应里没有 `X-RAG-Cache` 头）。
请求里那段 system 是内置「课程老师」人设的完整 724 字输出契约，太长，这里只留头尾：

```json
{
  "model": "qwen-plus",
  "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "temperature": 0, "seed": 20261104, "cache": true,
  "messages": [
    { "role": "system", "content": "你是高校《大模型应用开发》课程的指导老师……（724 字输出契约：选择题三行式——「答案：<字母> ｜ 竖线后抄题干里该选项的原文」+「依据：」带全算式 + 其余选项逐行「<字母> 不选：<错在哪>」；简答题【结论】【要点】【易错】；数字逐字照抄）" },
    { "role": "user", "content": "单选题：设关系R和S的属性个数分别为2和3，元组个数分别为3和4，则R×S运算的结果中，属性个数和元组个数分别是（ ）A 5和7 B 5和12 C 6和7 D 6和12" }
  ]
}
```

响应（真实抓包，**这一趟上游用了 15.00 秒**——同一条请求另外两次抓包是 4.89 秒和 5.12 秒，
耗时全看上游抖动，判断有没有命中不能看耗时，只能看 `X-RAG-Cache` 头和 `usage`）：

```json
{
  "model": "qwen-plus", "id": "chatcmpl-6585aed9-f8ed-9c5d-abac-76005153b99a",
  "created": 1793771408, "object": "chat.completion",
  "choices": [
    { "index": 0, "finish_reason": "stop", "message": { "role": "assistant",
      "content": "答案：B ｜ 5和12  \n依据：笛卡尔积R×S的属性个数 = R的属性个数 + S的属性个数 = 2 + 3 = 5；元组个数 = R的元组个数 × S的元组个数 = 3 × 4 = 12。  \nA 不选：属性个数正确（2+3=5），但元组个数错误（误用加法：3+4=7，而非乘法）。  \nC 不选：属性个数错误（误用乘法：2×3=6），元组个数也错误（3+4=7）。  \nD 不选：属性个数错误（2×3=6），元组个数正确（3×4=12），但属性数错即整体错。" } }
  ],
  "usage": { "total_tokens": 780, "completion_tokens": 183, "prompt_tokens": 597 }
}
```

**命中**（同一句原话再问一次，0.49 秒）。响应头是真实的（`question` 按 HTTP 头要求转成了 `\uXXXX`）：

```http
X-RAG-Cache: {"hit":true,"id":"q20261104134843-b658","score":1.0,"question":"\u5355\u9009\u9898\uff1a\u8bbe\u5173\u7cfbR\u548cS\u7684\u5c5e\u6027\u4e2a\u6570\u5206\u522b\u4e3a2\u548c3\uff0c\u5143\u7ec4\u4e2a\u6570\u5206\u522b\u4e3a3\u548c4\uff0c\u5219R\u00d7S\u8fd0\u7b97\u7684\u7ed3\u679c\u4e2d\uff0c\u5c5e\u6027\u4e2a\u6570\u548c\u5143\u7ec4\u4e2a\u6570\u5206\u522b\u662f\uff08 \uff09A 5\u548c7 B 5\u548c12 C 6\u548c7 D 6\u548c12"}
```

```json
{
  "model": "qwen-plus", "id": "chatcmpl-q20261104134843-b658",
  "created": 1793771323, "object": "chat.completion",
  "choices": [
    { "index": 0, "finish_reason": "stop", "message": { "role": "assistant",
      "content": "答案：B ｜ 5和12  \n依据：笛卡尔积R×S的属性个数 = R的属性个数 + S的属性个数 = 2 + 3 = 5；…（与首次那条**逐字节相同**，脚本比对结果 `true`）" } }
  ],
  "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 },
  "cached": true
}
```

`usage` 三个数全 0 是因为这一路根本没出网；`id` 直接沿用缓存条目的 id（`chatcmpl-` + 条目 id），
前端靠响应头里的 `hit/score/question` 在气泡上挂「缓存命中 1.00 · 0 token」的绿标。
命中知识库那条路时，`X-RAG-Sources` 也从缓存条目里**回放**，所以命中之后照样显示引用了哪几段、
「据[资料2]」的编号不会丢。

**这一层是「同题同答」的真正保证**。温度 0 + 固定 seed 只能保证「选哪个、什么形状」：
本机把上面那条请求的 `cache` 改成 `false` 连问三次（4.68 / 4.71 / 4.42 秒，780 / 781 / 770 token），
三份文本两两不同——`2+3=5` 有时写成 `2 + 3 = 5`，三条排除理由每次重排用词——
但「答案：B ｜ 5和12」这两个数值三次都没变。要连标点都不变，就得靠上面那个回放路径。

**流式同样走缓存**（同一句原话加 `"stream": true`，0.53 秒，`X-RAG-Cache` 头照样给）。
分片仍是标准 OpenAI 形状，全文一次给完，然后 `finish_reason` + `[DONE]`：

```text
data: {"id": "chatcmpl-q20261104134843-b658", "object": "chat.completion.chunk", "created": 1793771329, "model": "qwen-plus", "choices": [{"index": 0, "delta": {"role": "assistant", "content": "答案：B ｜ 5和12  \n依据：笛卡尔积R×S的属性个数 = …（整段答案一次给完）"}, "finish_reason": null, "logprobs": null}]}

data: {"id": "chatcmpl-q20261104134843-b658", "object": "chat.completion.chunk", "created": 1793771329, "model": "qwen-plus", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop", "logprobs": null}]}

data: [DONE]
```

**勾了知识库就换一个桶**（同一句原话，只把 `"rag"` 改成 `true`；真实抓包，5.23 秒、`total_tokens` 2309，
没有 `X-RAG-Cache` 头，而是带了 `X-RAG-Sources`）：

```http
X-RAG-Sources: [{"name":"README.md","i":16,"score":0.55},{"name":"README.md","i":14,"score":0.5113},{"name":"README.md","i":17,"score":0.507},{"name":"README.md","i":13,"score":0.5067}]
```

```json
{
  "model": "qwen-plus", "id": "chatcmpl-7d6cbd2d-57db-9883-8c3e-badea6b7a3e2",
  "created": 1793771414, "object": "chat.completion",
  "choices": [
    { "index": 0, "finish_reason": "stop", "message": { "role": "assistant",
      "content": "答案：B ｜ 5和12  \n依据：笛卡尔积运算的属性个数 = R的属性个数 + S的属性个数 = 2 + 3 = 5；元组个数 = R的元组个数 × S的元组个数 = 3 × 4 = 12。  \nA 不选：7是元组个数的加法结果（3+4=7），但笛卡尔积要求乘法，不是加法。  \nC 不选：6是属性个数的乘法结果（2×3=6），但属性个数应相加，不是相乘。  \nD 不选：6和12中6错，属性个数应为2+3=5，不是2×3=6；12正确但整体不匹配。" } }
  ],
  "usage": { "total_tokens": 2309, "completion_tokens": 178, "prompt_tokens": 2131 }
}
```

答案第一行仍是「答案：B ｜ 5和12」，但整段文本和上面那条纯温度 0 的**不是同一份**：
勾了知识库会往系统提示词里拼四段资料，措辞就跟着变了。两种答案都各有用处，
所以绝不能让带引用编号的那份回放给没勾知识库的问题——这就是作用域里要放「模式」的原因。

边界与失效规则（都是实测过的）：
- **作用域**：`sha1(模型 + 模式 + 所有 system 文本)` 的前 16 位。模式是 `rag`/`search` 开关加上请求里的温度，
  形如 `rag|t=0`、`|t=0`、`|t=0.7`。实测同一段 724 字人设、同一道选择题：检索关 t=0 是 `1dbd901c70b2c9fa`，
  检索开 t=0 是 `f2ec783a8e4d5a97`，检索关 t=0.7 是 `1ff71f7c51e2f9b2`，检索关 t=0.2 是 `c17174c598f76403`，
  四个桶互不复用。换人设（知识库问答角色是 `b8a7e999d6d51a08`）、换模型、改提示词同理——列表里会看到两条同样的问题、`scope` 不同。
- **参数指纹**：每条缓存记着写入时的 `EMBED_MODEL|DIM|topK|minScore|chunkChars|lib=`，末尾 `lib=` 是语料快照
  （库里文档份数 + 文件名集合的 sha1 前 8 位，例如 `1-43c3cb8e`）。改了 `RAG_MIN_SCORE`、重新切片之后旧条目不再命中，
  **上传或删除任何一份资料也一样让全部旧条目作废**（列表里标灰提示「参数或资料已变更，这条不再复用」）。
- **文档级联失效**：删除文档、或同名重新上传（`replace`）替换掉旧文档时，凡是引用过这些文档 id 的缓存条目一并删除。实测同名覆盖后 `lookup` 立刻 `hit: false`。
  只靠这条级联是不够的：**新增**资料时没有任何旧条目「引用」它，于是「先问过、后补资料」会回放一条资料还不存在时的旧答案
  ——2026-11-07 实测：15:38 在飞书问「WiFi密码是多少？」库里还没有那份 `ceshi1.md`（15:40 才入库），答案是不会答的拒答并被存进缓存；
  15:42 网页端同一个问题正常检索到新片段、答出密码，而 15:44 飞书再问仍然回放 15:38 那条（`diag` 里 `best: 1.0` 但 `stale: 1`）。
  把语料并进指纹之后这条路堵死了：同一批旧条目立刻全部 `stale: 1`、不再回放。
- **不进缓存的请求**：答案是空的、`"mcp": true`（有实时数据）、多模态（`content` 是数组，识图取决于具体那张图）、`cache` 为 `false`（温度调上去的角色）都不查也不写。流式被中途「停止」打断、没看到 `[DONE]` 的半截答案也不写。
- **阈值 0.80 的来历**：库里存着「文档片段的检索相似度门槛默认是多少？」，实测同义改写的相似度是
  0.9971 / 0.9959 / 0.8613 / 0.8409（越改越口语就越低，但都过 0.80；前两个数就是 8.6 那两次探测），
  而跨话题那句「那这道笛卡尔积的题选什么」只有 **0.4137 / 0.4002**（两个不同存储问题各测一次，都在 8.6）
  ——所以卡 0.80：改写命中、跨话题不串味。原来定的是 0.92，同义改写几乎全漏。宁可漏命中，也不要答错。
- **淘汰**：超过 `CACHE_MAX_ENTRIES`（默认 200）条时按「最久没被命中」淘汰；每次命中都会把该条的 `updatedAt` 推到当前时间，常用的答案不会被挤掉。

---

## 6. 文生图 / 图生图 `POST /api/image`

一个接口两种用法，靠 `kind` 区分。上游是百炼 `qwen-image` 多模态生成端点，同步返回。

### 6.1 文生图

请求：

```json
{
  "kind": "t2i",
  "prompt": "一只戴着宇航头盔的橘猫，星空背景，柔和光影",
  "model": "qwen-image-2.0",
  "size": "1024*1024",
  "n": 1,
  "negativePrompt": "文字，水印"
}
```

### 6.2 图生图

参考图直接传本机读出的 base64 data URL（不需要图床），最多 3 张：

```json
{
  "kind": "i2i",
  "prompt": "把这张图改成水彩画风格，保留原来的构图",
  "size": "1024*1024",
  "n": 2,
  "images": [ "data:image/png;base64,iVBORw0KG…" ]
}
```

### 6.3 响应

后端把上游返回的临时图片地址（`*.aliyuncs.com`，会校验域名）代取回本机，转成 data URL 一起回传，
所以前端下载图片不跨域、也不怕链接过期：

```json
{
  "ok": true,
  "images": [ "data:image/png;base64,iVBORw0KG…" ],
  "model": "qwen-image-2.0",
  "size": "1024*1024",
  "seconds": 18.4
}
```

参数校验：`kind` 只能是 `t2i`/`i2i`；`prompt` 非空；`size` 必须在 `/api/health` 给出的列表里；
`n` 是 1~`imageMaxCount`；`i2i` 必须带 1~3 张 `data:image/` 开头的参考图。不满足时返回 `400 {"detail": "…"}`，
上游报错或没出图返回 `502`。出图是同步等待，一次 10~40 秒。

---

## 7. 历史对话 json 文件

每个用户一个文件：`history/<用户名>.json`，结构是 `{角色 id: [消息, …]}`。
后端只保留 `role`/`content`/`ts` 以及 `search`/`error`/`model`/`tools`/`rag`/`cache` 这几个字段，
单条内容截到 20000 字，每个角色最多留最近 400 条。`cache` 形如
`{"hit": true, "score": 0.8239, "question": "知识库检索的相似度阈值默认是多少？"}`，
刷新页面后气泡上的「缓存命中」徽标靠它复现。

### 7.1 读指定历史对话 `GET /api/history?role=teacher`

```json
{
  "ok": true,
  "role": "teacher",
  "messages": [
    { "role": "user", "content": "帮我看看这段代码有什么问题", "ts": 1792724887123 },
    { "role": "assistant", "content": "……", "ts": 1792724891002,
      "tools": [ { "name": "get_weather", "args": { "city": "杭州", "days": 1 } } ] }
  ]
}
```

没聊过时 `messages` 是空数组。

### 7.2 一次读回全部 `GET /api/history/all`

登录后调用，目录里有什么角色就发什么，前端自己加的自定义角色也能取回：

```json
{ "ok": true, "conversations": { "teacher": [ … ], "myRole": [ … ] } }
```

### 7.3 保存 `POST /api/history`

每轮对话结束后整段覆盖该角色：

```json
{ "role": "teacher", "messages": [ { "role": "user", "content": "你好", "ts": 1792724887123 } ] }
```

响应：

```json
{ "ok": true, "role": "teacher", "saved": 1 }
```

### 7.4 清空 `POST /api/history/clear`

```json
{ "role": "teacher" }
```

`role` 传 `"all"` 则清空该用户全部角色的历史。响应：

```json
{ "ok": true, "cleared": "teacher" }
```

历史里的角色 id 不查白名单（要容纳自定义角色），但会校验形状：只允许中文、字母、数字、下划线、短横线，
含 `/`、`\`、`..` 的一律 `400 非法的角色 id`，防止越权写到别人的文件或项目外的路径。

---

## 7.5 在线调试

FastAPI 自带文档页，启动后直接访问：

| 地址 | 说明 |
| --- | --- |
| `http://127.0.0.1:8000/docs` | Swagger UI，22 个接口都能在这里直接发请求试 |
| `http://127.0.0.1:8000/redoc` | 同一份 schema 的另一种排版 |
| `http://127.0.0.1:8000/openapi.json` | 机器可读的接口定义 |

`/docs` 里先调 `/api/login`，浏览器就会带上会话 Cookie，后面的接口可以直接试。
schema 由 FastAPI 自动生成，里面不含任何密钥。

---

## 8. RAG 知识库接口

一句概括：**上传文档 → 切片 → 向量化 → 存本地 JSON → 检索时算余弦相似度 → 把最相关的几段拼进提示词**。
向量化调百炼的 OpenAI 兼容端点 `POST {baseUrl}/embeddings`（模型 `text-embedding-v3`，1024 维），
复用 `config.py` 里那把对话 Key，没有第二个密钥、没有向量数据库、没有新增第三方依赖。
8.1~8.4 是文档索引，8.5~8.7 是架在同一套向量集合层上的**问答缓存**（对话里的命中路径见 5.6）。

索引存储是**一份文档一个文件**：`kb/<文档 id>.json`。

```json
{
  "id": "d20261102154506-1dda",
  "name": "RAG演示资料.md",
  "model": "text-embedding-v3",
  "dim": 1024,
  "createdAt": 1793605506,
  "chars": 239,
  "chunks": [
    { "i": 0, "text": "# RAG 演示资料\n\n本次演示的提交编号是 AICHAT-2026-1147。…", "vec": [0.01234, -0.04567, "…共 1024 个数"] }
  ]
}
```

文档 id 由后端生成（`d` + 14 位时间戳 + `-` + 4 位随机十六进制），显示名只是 JSON 里的一个字段，
**不参与路径拼接**，所以文件名带 `/`、`..` 也写不到项目外面去。写入走 `.tmp` + `os.replace`，外面加一把进程锁。

问答缓存存在**另一个集合**里：`kb/collections/qa.json`。它的读写由 `vstore.py` 负责，是一层和文档索引无关的
通用向量集合（collection）能力——集合按名隔离、按 id 增量 upsert / 删除、元数据过滤、超过上限按最近最少使用淘汰、
自带 stats 统计，接口形状对着向量数据库的 collection 设计，只是实现是纯 Python + JSON 落盘
（下面这份是**形状示意**，字段值取自早先一次写入；交付时这个集合是空的，只有 `name` / `model` / `dim` 那几个头字段）：

```json
{
  "name": "qa", "model": "text-embedding-v3", "dim": 1024,
  "createdAt": 1793762004, "updatedAt": 1793763401,
  "items": [
    {
      "id": "q20261104113021-456c", "text": "知识库检索的相似度阈值默认是多少？",
      "vec": [-0.09941, -0.02412, "…共 1024 个数"],
      "hits": 2, "createdAt": 1793763021, "updatedAt": 1793763207,
      "meta": {
        "q": "知识库检索的相似度阈值默认是多少？",
        "answer": "知识库检索的相似度阈值默认是 0.45。  \n据[资料2]：…",
        "scope": "c915d3221af7556a",
        "fp": "text-embedding-v3|1024|k4|s0.45|c500|lib=1-43c3cb8e",
        "model": "qwen-plus",
        "sources": [ { "name": "README.md", "i": 16, "score": 0.7229 } ],
        "docs": [ "d20261104112046-8225" ],
        "ts": 1793763021
      }
    }
  ]
}
```

集合名要过 `^[a-z][a-z0-9_]{1,30}$`、条目 id 要过 `^[A-Za-z0-9_-]{1,48}$`，所以 `name` 拼出来的路径只会落在
`kb/collections/` 里面。`meta.scope` 是 `sha1(模型 + 模式 + 所有 system 文本)` 的前 16 位，模式就是这次请求的
「检索/联网开关 + 温度」（形如 `rag|t=0`）；`meta.fp` 是检索参数指纹，末尾还带一份语料快照 `lib=`，
两个数怎么用来失效缓存见 5.6 和 8.6。

### 8.1 知识库状态 `GET /api/rag/status`

响应 `200`（真实抓包，交付状态：README.md 加上一份 21 字的测试资料 `ceshi1.md`，问答缓存已清空）：

```json
{
  "ok": true,
  "docs": [
    { "id": "d20261107154002-7e75", "name": "ceshi1.md", "chars": 21,
      "chunks": 1, "model": "text-embedding-v3", "dim": 1024, "createdAt": 1794037202, "current": true },
    { "id": "d20261104134827-c8d5", "name": "README.md", "chars": 19634,
      "chunks": 59, "model": "text-embedding-v3", "dim": 1024, "createdAt": 1793771307, "current": true }
  ],
  "totalChunks": 60,
  "totalChars": 19655,
  "model": "text-embedding-v3",
  "dim": 1024,
  "topK": 4,
  "minScore": 0.45,
  "chunkChars": 500,
  "maxDocChars": 80000,
  "outdated": [],
  "cache": { "items": 0, "totalHits": 0, "bytes": 120,
             "minScore": 0.8, "maxEntries": 200, "enabled": true }
}
```

`docs` 按入库时间倒序，所以后上传的排在前面。`ceshi1.md` 是留着做检索演示的那份小资料（内容就一句
「WiFi密码是多少？密码是12345678」），它在 8.4 的检索里以 0.9251 排第一。

下面 8.2 ~ 8.6 的报文都是**只有一份 README 时**打的真实抓包，那时 `candidates` 是 59；
现在同样查询会是 60（多出的那一片就是 `ceshi1.md#0`），其余数字不变。

`current: false` 表示这份文档入库时用的向量模型或维度和现在配置不一致，旧向量不可比，检索时会被跳过并计入
`outdated`，页面上显示成「模型已变更，需重新上传」。

抓包里的文档 id 只对当时那一次入库有效（重新入库就会换），不是固定值——页面上的「已入库文档」列表
才是当前真实状态。

### 8.2 上传文档 `POST /api/rag/doc`

请求（`text` 是前端用 `FileReader` 读出的纯文本，`.md` `.markdown` `.txt` `.text` 都收）：

```json
{ "name": "RAG演示资料.md", "text": "# RAG 演示资料\n\n本次演示的提交编号是 AICHAT-2026-1147。…" }
```

可选的 `"replace": true`（缺省就是 `true`）表示**同名覆盖**：先把库里同名文档的索引文件删掉再写新的，
所以改了 README 重新上传一次就行，不会攒出一堆同名的旧版本。覆盖时响应里会带回被替换掉的旧 id。
传 `"replace": false` 则同名也各存一份，检索时两份一起参与。

响应 `200`（真实抓包，覆盖上传 README.md）：

```json
{
  "ok": true,
  "doc": {
    "id": "d20261104134827-c8d5", "name": "README.md", "chars": 19634, "chunks": 59,
    "model": "text-embedding-v3", "dim": 1024, "createdAt": 1793771307, "seconds": 5.3,
    "replaced": ["d20261104134725-5706"]
  }
}
```

`seconds` 是切片 + 向量化的耗时，主要由批次数和网络往返决定（20 片一批 2 次请求，59 片 3 次）：
239 字 3 片不到 1 秒，19634 字 59 片实测 5.3 秒，另一份 7600 字 25 片当时实测 22 秒（上游偶尔就是很慢，
所以这个数只能当量级看）。

切片规则（`rag.split_chunks`）：先按 Markdown 标题 `\n(?=#{1,6}\s)` 切大段，每段再按句子装箱到
`RAG_CHUNK_CHARS`（默认 500）字左右，相邻块之间带回 `RAG_CHUNK_OVERLAP`（默认 80）字，
续接的块会重新冠上它所属的标题，免得「第 2 片」看不出自己在讲哪一节。

失败都是 `400`：

```json
{ "detail": "文档太长（80001 字，上限 80000 字），请先拆分" }
{ "detail": "文档没有可用的正文" }
{ "detail": "文档名不能为空" }
{ "detail": "切片过多（260 片，上限 200 片），请缩短文档" }
```

前端一次最多传 800 KB 的文件，多个文件按顺序一份一份入库，每份完成就刷新列表。

### 8.3 删除文档 `POST /api/rag/doc/remove`

请求（这份抓包删的是当时那份《RAG演示资料.md》，交付库里没有它，现在留着的是 README.md 和 `ceshi1.md`，见 8.1）：

```json
{ "id": "d20261104114215-7592" }
```

响应 `200`（真实抓包；删之前缓存里有 1 条问答引用了这份文档）：

```json
{ "ok": true, "removed": "d20261104114215-7592", "cacheDropped": 1 }
```

`cacheDropped` 是这次被连带删掉的**问答缓存**条数——删文档前会先看清哪些缓存引用过它，否则下次会秒回一个
基于已删资料的答案。同名覆盖（8.2 的 `replace`）走的是同一段逻辑，只是响应里用 `replaced` 表示替换了谁。
id 不合规则 `400 {"detail": "非法的文档 id"}`（空串、`../x` 都算），
文件不存在是 `404 {"detail": "没有这个文档，或它已经被删掉了"}`。

### 8.4 检索调试 `POST /api/rag/search`

只看命中了哪几段、相似度多少，**不调大模型、不花 token**，是调 `topK` / `minScore` 的工具。

请求：

```json
{ "query": "文档片段的检索相似度门槛默认是多少？", "topK": 4, "minScore": 0.45 }
```

`topK`、`minScore` 可省略，省略就用 `config.py` 里的默认值；`topK` 会被夹到 1~10。
`docIds`（数组，可省略）是**元数据过滤**：只在指定的那几份文档里检索，用于「只查这一份」这种需求；
里面出现非法 id 直接 `400 {"detail": "非法的文档 id"}`。

响应 `200`（真实抓包，打这份时库里只有 README.md 一份、59 片。`text` 是切片原文，最长 2000 字，这里截断了）：

```json
{
  "ok": true,
  "hits": [
    { "rank": 1, "doc": "d20261104134827-c8d5", "name": "README.md", "i": 33, "score": 0.8058,
      "text": "### 问答缓存：换个问法也秒回\n|---|---|---|\n| 文档片段的检索相似度门槛默认是多少？（首次真正提问） …" },
    { "rank": 2, "doc": "d20261104134827-c8d5", "name": "README.md", "i": 28, "score": 0.7737,
      "text": "### 参数（`config.py`，改完要重启后端）\n**调参实测**：早前用本课程三份文档测的时候，真正相关的片段相…" },
    { "rank": 3, "doc": "d20261104134827-c8d5", "name": "README.md", "i": 23, "score": 0.7212,
      "text": "### 怎么用\n还能输入一句话**只探测不调模型**，以及单条删除 / 一键清空\n\n库里已经存了一份本 README 作…" },
    { "rank": 4, "doc": "d20261104134827-c8d5", "name": "README.md", "i": 27, "score": 0.6824,
      "text": "### 参数（`config.py`，改完要重启后端）\n| `CACHE_MIN_SCORE` | `0.80` | *…" }
  ],
  "diag": { "query": "文档片段的检索相似度门槛默认是多少？", "docs": 1, "chunks": 59, "skipped": 0,
            "filtered": 0, "topK": 4, "minScore": 0.45, "model": "text-embedding-v3", "candidates": 59 },
  "seconds": 0.41
}
```

这四片正是讲问答缓存和参数表的那几段，所以「门槛默认是多少」这种问法能直接命中——它也是 5.6 里
「换个问法照样秒回」的同一批语料。

另份早先的抓包（当时库里有三份课程资料，用来看**多份文档混在一起排序**长什么样）：

```json
{
  "ok": true,
  "hits": [
    { "rank": 1, "doc": "d20261102154506-1dda", "name": "RAG演示资料.md", "i": 0,
      "score": 0.6962, "text": "# RAG 演示资料\n\n本次演示的提交编号是 AICHAT-2026-1147。…" },
    { "rank": 2, "doc": "d20261102153526-82b1", "name": "第2章-向量数据库与RAG.md", "i": 0,
      "score": 0.5937, "text": "# 第 2 章 向量数据库与 RAG\n\n本节课堂演示编号是 RAG-UI-2026-8842。…" },
    { "rank": 3, "doc": "d20261102153810-d277", "name": "GBK课件-提示词工程.txt", "i": 0,
      "score": 0.525, "text": "# 提示词工程笔记（GBK 编码样例）…" },
    { "rank": 4, "doc": "d20261102154506-1dda", "name": "RAG演示资料.md", "i": 2,
      "score": 0.5082, "text": "## 相似度阈值\n\n用 text-embedding-v3 生成 1024 维向量…" }
  ],
  "diag": { "query": "提交编号是多少", "docs": 3, "chunks": 8, "skipped": 0,
            "topK": 4, "minScore": 0.45, "model": "text-embedding-v3", "candidates": 8 },
  "seconds": 0.41
}
```

`diag` 用来说清「为什么没命中」：`docs` / `chunks` 是扫了多少份、多少片，`skipped` 是跳过的旧向量数，
`candidates` 是参与排序的候选数，`filtered` 是因 `docIds` 被排除掉的片数。
`rank` 从 1 开始且**在阈值过滤之后**才编号，所以注入提示词时不会出现 `[资料1] [资料3]` 这种跳号。

`docIds` 过滤的两个对照（真实抓包，打这两份时库里只有 README.md 一份、59 片，查询都是「阈值」）：

```json
{ "hits": 4, "diag": { "query": "阈值", "docs": 1, "chunks": 59, "skipped": 0, "filtered": 0,
  "topK": 4, "minScore": 0.45, "model": "text-embedding-v3",
  "docIds": ["d20261104134827-c8d5"], "candidates": 59 } }

{ "hits": 0, "diag": { "query": "阈值", "docs": 1, "chunks": 0, "skipped": 0, "filtered": 59,
  "topK": 4, "minScore": 0.45, "model": "text-embedding-v3",
  "docIds": ["d20260101000000-ffff"], "candidates": 0 } }
```

第一份命中的四片分数是 0.6405 / 0.5968 / 0.5951 / 0.5891，都是讲缓存和参数表的那几段。
第二份是查一个不存在 / 没选中的文档 id：59 片全被 `filtered` 掉，`candidates` 归零，所以 0 命中——
过滤发生在算相似度之前，不是算完再丢。

无关问题能筛掉多少，取决于库里装着什么。早先用三份课程资料时，`今天晚饭吃什么` 最高只有 0.41，
直接 0 命中：

```json
{ "ok": true, "hits": [], "diag": { "query": "今天晚饭吃什么", "docs": 3, "chunks": 8,
  "skipped": 0, "topK": 4, "minScore": 0.45, "model": "text-embedding-v3", "candidates": 8 },
  "seconds": 0.46 }
```

**换成现在这份讲阈值的 README 当语料，同一句就压线了**（真实抓包，交付状态）：

```json
{
  "ok": true,
  "hits": [
    { "rank": 1, "doc": "d20261104134827-c8d5", "name": "README.md", "i": 27, "score": 0.5038,
      "text": "### 参数（`config.py`，改完要重启后端）\n| `CACHE_MIN_SCORE` | `0.80` | *…" },
    { "rank": 2, "doc": "d20261104134827-c8d5", "name": "README.md", "i": 28, "score": 0.4806,
      "text": "### 参数（`config.py`，改完要重启后端）\n**调参实测**：早前用本课程三份文档测的时候，真正相关的片段相…" }
  ],
  "diag": { "query": "今天晚饭吃什么", "docs": 1, "chunks": 59, "skipped": 0, "filtered": 0,
            "topK": 4, "minScore": 0.45, "model": "text-embedding-v3", "candidates": 59 },
  "seconds": 0.42
}
```

一个 0.5038 过了线、另一个 0.4806 没过——语料本身在讲「阈值」，「吃什么」里的「什么」就蹭到了分。
这不代表阈值定错了：过线的这一段拼进提示词，模型看到的仍是参数表，答不出晚饭，只是白占一段预算。
想让无关问题彻底空手，把 `RAG_MIN_SCORE` 提到 0.50~0.55，代价是同义改写也更容易被挡（README 第六节记了这个取舍）。

前端「知识库 → 检索测试」就是调这个接口：过了阈值但只有 0.45~0.50 的卡片显示成灰色（相关但不强），
0 命中时告诉你候选片数和当前阈值，据此决定是降阈值还是改文档。
失败 `400`：`{"detail": "检索内容不能为空"}`、`{"detail": "topK 必须是数字"}`、`{"detail": "minScore 必须是数字"}`、
`{"detail": "docIds 必须是数组"}`。

### 8.5 问答缓存列表 `GET /api/rag/cache?limit=50`

看缓存里存了哪些问题、各自被复用几次、引用了哪几段、归哪个作用域。`limit` 默认 50、最大 200，按 `updatedAt` 倒序。

响应 `200`（真实抓包，此时有 2 条。**同一个问题在两个不同作用域各存了一条**——第 1 条是没勾知识库问的，
第 2 条是勾着知识库问的，所以两份答案各自回放各自的，不会串）：

```json
{
  "ok": true,
  "items": [
    {
      "id": "q20261104134843-b658",
      "question": "单选题：设关系R和S的属性个数分别为2和3，元组个数分别为3和4，则R×S运算的结果中，属性个数和元组个数分别是（ ）A 5和7 B 5和12 C 6和7 D 6和12",
      "answer": "答案：B ｜ 5和12  \n依据：笛卡尔积R×S的属性个数 = R的属性个数 + S的属性个数 = 2 + 3 = 5；元组个数 = R的元组个数 × S的元组个数 = 3 × 4 = 12。  \nA 不选：属性个数正确（2+3=5），但元组个数错误（误用加法：3+4=7，而非乘法）。  \nC 不选：属性个数错误（误用",
      "hits": 2, "scope": "1dbd901c70b2c9fa", "sources": [], "docs": [],
      "model": "qwen-plus",
      "createdAt": 1793771323, "updatedAt": 1793771329, "current": true
    },
    {
      "id": "q20261104134848-1e22",
      "question": "单选题：设关系R和S的属性个数分别为2和3，元组个数分别为3和4，则R×S运算的结果中，属性个数和元组个数分别是（ ）A 5和7 B 5和12 C 6和7 D 6和12",
      "answer": "答案：B ｜ 5和12  \n依据：笛卡尔积运算的属性个数 = R的属性个数 + S的属性个数 = 2 + 3 = 5；元组个数 = R的元组个数 × S的元组个数 = 3 × 4 = 12。  \nA 不选：7是元组个数的加法结果（3+4=7），但笛卡尔积要求乘法，不是加法。  \nC 不选：6是属性个数的乘法结果（2×3",
      "hits": 0, "scope": "f2ec783a8e4d5a97",
      "sources": [ { "name": "README.md", "i": 16, "score": 0.55 },
                   { "name": "README.md", "i": 14, "score": 0.5113 },
                   { "name": "README.md", "i": 17, "score": 0.507 },
                   { "name": "README.md", "i": 13, "score": 0.5067 } ],
      "docs": [ "d20261104134827-c8d5" ],
      "model": "qwen-plus",
      "createdAt": 1793771328, "updatedAt": 1793771328, "current": true
    }
  ],
  "stats": { "name": "qa", "items": 2, "model": "text-embedding-v3", "dim": 1024,
             "distinctDims": [1024], "createdAt": 1793762004, "updatedAt": 1793771329,
             "bytes": 21892, "totalHits": 2 },
  "minScore": 0.8, "maxEntries": 200, "enabled": true, "ttl": 0, "collection": "qa"
}
```

两条 `question` 一模一样，`scope` 差在模式串（`|t=0` 对 `rag|t=0`），`answer` 的措辞也各有不同——
「依据：笛卡尔积R×S的」对「依据：笛卡尔积运算的」：第 1 条是纯温度 0 现生成的，第 2 条是检索注入后现生成的，
两次都没被对方的桶挡住。这正是缓存不会串味的证据，也是 5.6 说「逐字一致由回放兜住」的那个回放源
（第 1 条 `hits: 2` = 非流式命中一次 + 流式命中一次）。

`answer` 只回前 160 字（`rag.cache_list` 里 `[:160]`），列表页够用，别让前端以为那是全文；
缓存里存的是完整答案，命中时回放的是全文。

`current: false` 表示这条写入时的检索参数指纹和现在不一致（改了 `RAG_MIN_SCORE`、`RAG_TOP_K`、切片长度、向量模型，
或者**上传/删除过任何一份资料**——指纹里的 `lib=` 段变了），不会再被复用。`hits` 只在**真的命中**时才 +1，同时把 `updatedAt` 推到当前时间，供 LRU 淘汰用。
`bytes` 是 `kb/collections/qa.json` 的实际大小，一条 1024 维向量摊下来约 10 KB。

上面这份抓包之后，交付前又点了一次「清空缓存」（8.7），所以 8.1 的交付状态是 `cache.items: 0`、
`qa.json` 只剩 120 字节的空壳。演示时第一次提问会真的走模型，第二次起才看到绿标。
（2026-11-07 接飞书时又跑了一遍同样的两问，换词那句实测 `score: 0.8613`、`diag: {items: 1, candidates: 1, minScore: 0.8}`，
和 8.6 那份抓包对得上；机器人不带 system 人设，所以它的作用域是另一个桶 `2681e37d80049d80`，不是页面上那个 `1dbd901c70b2c9fa`。）

### 8.6 缓存探测 `POST /api/rag/cache/lookup`

**只查缓存、不调对话模型、也不新增条目**，用来看这句问题会不会命中、最像的一条有几分。会调一次 `embeddings`（问题要向量化），
因为不走生成所以不产生对话费用；但**命中时照样记一次复用**（`hits` +1、`updatedAt` 推到当前，走的是回放同一个
`bump_hits`），所以它不是无副作用的 dry-run，别拿它反复探测同一个问题来"白嫖"统计数。

请求（`messages` 可省略；带上它是为了让作用域和真实对话那条路一致——换了 system 就是另一个作用域。
`rag` 和 `temperature` 同理，前端探测时会把当前勾选状态和这个角色的温度一起传过来）：

```json
{ "query": "那这道笛卡尔积的题选什么", "model": "qwen-plus", "rag": false, "temperature": 0,
  "messages": [ { "role": "system", "content": "你是高校《大模型应用开发》课程的指导老师……（724 字）" },
                { "role": "user", "content": "x" } ] }
```

响应 `200`（真实抓包，一次跑完的四连探测。第 1 份是**缓存刚清空时**探的，所以 `items: 0`、`best` 是 `null`）：

```json
{
  "ok": true, "hit": false, "score": null, "question": null, "answer": null,
  "scope": "1dbd901c70b2c9fa",
  "diag": { "items": 0, "candidates": 0, "skipped": 0, "filtered": 0, "minScore": 0.8, "best": null },
  "seconds": 10.46
}
```

然后把「文档片段的检索相似度门槛默认是多少？」真问了一遍（关检索、温度 0，答案写进缓存），
接着探两个换词的问法——**都命中**：

```json
{ "ok": true, "hit": true, "score": 0.9971, "question": "文档片段的检索相似度门槛默认是多少？",
  "answer": "题干信息不足：缺＜课程指定教材或课件中该参数的明确定义位置＞", "scope": "1dbd901c70b2c9fa",
  "diag": { "items": 1, "candidates": 1, "skipped": 0, "filtered": 0, "minScore": 0.8, "best": 0.9971 },
  "seconds": 0.53 }

{ "ok": true, "hit": true, "score": 0.8613, "question": "文档片段的检索相似度门槛默认是多少？",
  "answer": "题干信息不足：缺＜课程指定教材或课件中该参数的明确定义位置＞", "scope": "1dbd901c70b2c9fa",
  "diag": { "items": 1, "candidates": 1, "skipped": 0, "filtered": 0, "minScore": 0.8, "best": 0.8613 },
  "seconds": 10.39 }
```

两份分数对得上 README 第六节那张表（「的」字挪个位置 0.9971，「文档片段→知识库」「门槛→阈值」都换词 0.8613）。
**答案本身是「题干信息不足」而不是一个数字，这也是对的**：这一串探测全程没勾知识库，
而「门槛默认值」是本项目的参数、只写在 README 里，模型按契约不编——勾上知识库再问才是 README 演示里那个 0.45，
那是另一个作用域（`f2ec783a8e4d5a97`），缓存里各存各的。缓存照原样回放这句「信息不足」，一次没改。

再探一个跨话题的句子，同一个作用域里最像的只有 0.4002，离 0.80 差得远，所以不命中：

```json
{
  "ok": true, "hit": false, "score": null, "question": null, "answer": null,
  "scope": "1dbd901c70b2c9fa",
  "diag": { "items": 1, "candidates": 1, "skipped": 0, "filtered": 0, "minScore": 0.8, "best": 0.4002 },
  "seconds": 0.44
}
```

另份早先的抓包（当时库里 3 条：2 条同属「检索关 + t=0」，1 条是「检索开」的，所以 `filtered: 1`）：

```json
{
  "ok": true, "hit": false, "score": null, "question": null, "answer": null,
  "scope": "8346af448a85be8c",
  "diag": { "items": 3, "candidates": 2, "skipped": 0, "filtered": 1, "minScore": 0.8, "best": 0.5081 },
  "seconds": 0.51
}
```

`diag` 是调阈值时最有用的部分：`items` 是集合里的总条数，`candidates` 是同一作用域下可比的条数，
`filtered` 是因作用域不同被排除的条数（提示词、模型、检索开关或温度换了），`skipped` 是维度不同的旧向量条数，
`best` 是**没过滤阈值时**最像的一条有几分。所以 `hit: false` 时能看到「差多少才够」，例如 `best: 0.7945` 对 `minScore: 0.8`。
上面四连探测里有两次 `seconds` 是 10.4 秒——探测要调一次 `embeddings`，上游偶尔就是慢，
**判断有没有命中永远看 `hit` / `score` 和 `X-RAG-Cache` 头，别看耗时**。

失败 `400`：`{"detail": "检索内容不能为空"}`、`{"detail": "向量模型不可用…"}`。

### 8.7 清空缓存 `POST /api/rag/cache/clear`

```json
{ "ids": ["q20261104135858-44cf"] }
```

`ids` 省略或传空数组就是整份清空。响应 `200`（真实抓包，交付前那次清空——集合里只剩刚才探测写入的 1 条，
删掉之后 `bytes` 回到 120 的空壳）：

```json
{ "ok": true, "removed": 1,
  "stats": { "name": "qa", "items": 0, "model": "text-embedding-v3", "dim": 1024,
             "distinctDims": [], "createdAt": 1793762004, "updatedAt": 1793771950,
             "bytes": 120, "totalHits": 0 } }
```

`ids` 不是数组时 `400 {"detail": "ids 必须是数组"}`。清空只动 `kb/collections/qa.json`，文档索引（`kb/*.json`）不受影响；
反过来删文档会自动挑出引用过它的缓存条目，不用手动清（见 8.3）；**新增**文档不用清也不用手动调——新文档的 id 进了
`fp` 的 `lib=` 段，所有旧条目当场 `current: false`（见 5.6）。

### 8.8 文件编码

上传时前端先按 UTF-8 严格解码，失败再退回 GBK（不少课程课件是记事本另存为 GBK 的），并去掉 BOM。
上面那份 `GBK课件-提示词工程.txt` 就是 GBK 文件，入库后中文检索正常，说明这条回退生效。

---

## 9. 静态资源与安全边界

后端把项目根目录挂在 `/` 上托管页面，因此加了一道中间件拦截源码与数据文件下载：

```http
GET /config.py   → 404 Not Found
GET /users.json  → 404 Not Found
GET /history/mcp_ui_test.json → 404 Not Found
GET /kb/d20261102154506-1dda.json → 404 Not Found
GET /kb/collections/qa.json → 404 Not Found
```

`__pycache__`、`.py`、`.log`、`.ini`、`.json` 结尾的路径一律 404，所以上面的向量索引文件
`kb/*.json` 和问答缓存 `kb/collections/qa.json`（里面是完整答案）也只能通过 `/api/rag/*` 接口访问，
不能被浏览器直接下载；`/js/app.js`、`/css/style.css`、`/index.html` 正常返回。

## 10. 图片理解

侧栏「对话 → 图片理解」不发新接口，复用 `POST /api/chat`：图片在前端读成 data URL，
和文字一起放进多模态的 `content` 数组，模型名换成 `visionModel`（`qwen3-vl-plus`）。

```json
{
  "model": "qwen3-vl-plus",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "请详细描述这张图片的内容。" },
        { "type": "image_url", "image_url": { "url": "data:image/png;base64,iVBORw0KG…" } }
      ]
    }
  ]
}
```

响应结构同 5.1。限制：只接受 `image/*`、单张不超过 4MB。
侧栏的「图片处理」分组指的是下面两个出图接口（6.1 文生图 / 6.2 图生图），不是本地编辑功能。

---

## 11. 附录：可选的飞书机器人接入层 `feishu_bot.py`

这一节不在课程评分要求里，多出来给的是一个接入层演示：把上面那套接口接到飞书的聊天窗口，
`api.py` 一行没改，机器人走的还是 `/api/login` + `/api/chat`。
不需要演示的话把 `feishu_bot.py` 整个删掉，前面 1~10 节的功能一个都不受影响。

### 11.1 链路

```
飞书 App →（WebSocket 长连接）→ feishu_bot.py → 本机 POST /api/login
                                                      ↓
              原会话回复  ←  一条消息（含来源注脚）  ←  POST /api/chat
```

机器人先用演示账号（`config.py:101-102`）登录，拿到和浏览器同一条路的 `ai_session` cookie，
之后每次请求都带上。所以历史、知识库、缓存都按这个账号计，不是另开的一套。

### 11.2 跑法

```
python api.py                                  终端 1，先起后端
python feishu_bot.py                           终端 2，起长连接
python feishu_bot.py --selftest 阈值默认是多少   不连飞书，只验后端这一段
```

`--selftest` 只依赖 `requests`，没装飞书 SDK 也能跑，作用是先把「本机后端答得对」和
「飞书那一头连得上」分开验证，出问题时知道该查哪一段。

### 11.3 依赖与凭证

| 项 | 位置 | 说明 |
| --- | --- | --- |
| `lark-oapi` | `pip install lark-oapi` | 本项目的可选依赖，没装只影响这一节 |
| `FEISHU_APP_ID` | `config.py:94` | 飞书开放平台「凭证与基础信息」里那串 `cli_` 开头的 ID |
| `FEISHU_APP_SECRET` | `config.py:95` | 从环境变量读，文件里恒为空 —— 和 `config.py:9` 的 `API_KEY` 同一个理由（README 第一节），提交的那份不带任何密钥 |
| `FEISHU_ENCRYPT_KEY` / `FEISHU_VERIFY_TOKEN` | `config.py:97-98` | 长连接模式用不到，留空 |

Secret 的填法：`setx FEISHU_APP_SECRET "你的Secret"`，重开终端才生效。
`FEISHU_CONTEXT_TURNS`（`config.py:104`）是每个飞书会话记住几轮，默认 6。

### 11.4 飞书后台要做的四步（少一件就是「已读不回」）

1. 创建自建应用，并勾选「机器人」能力；
2. 权限：`im:message.p2p_msg:readonly`、`im:message.group_at_msg:readonly`、`im:message:send_as_bot`；
3. 「事件与回调」→ 订阅方式选**使用长连接接收事件** → 添加事件 `im.message.receive_v1`；
4. 创建版本并**发布**——不发布，前三步配的权限和事件都不会生效。

为什么是长连接不是回调 URL：回调要公网 HTTPS + 域名 + 证书，而本项目 `HOST` 故意只绑
`127.0.0.1`（见第 9 节的安全边界）；长连接是机器人主动连飞书，机器能出网就行。

### 11.5 机器人发给 `/api/chat` 的东西

```json
{
  "model": "qwen-plus",
  "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "messages": [
    { "role": "user", "content": "知识库检索的相似度阈值默认是多少？" },
    { "role": "assistant", "content": "……上一轮的答案……" },
    { "role": "user", "content": "那问答缓存呢？" }
  ],
  "temperature": 0,
  "seed": 20261104,
  "cache": true,
  "rag": true
}
```

`messages` 带的是本会话最近 `FEISHU_CONTEXT_TURNS` 轮，所以连着问「那……呢」这种指代能接上。
最后一行的字段按模式换：`/rag` → `"rag": true`；`/plain` → 不加；`/search` → `"enable_search": true`；
`/weather` → `"mcp": true`。响应结构和 5.1 一致，机器人取 `choices[0].message.content`。

`temperature` 锁 0、`seed` 固定、`cache` **显式传 true** 这三样是有原因的：后端在 `cache` 不传时
只跟着 `rag` 走（见 5.6），`/plain` 和 `/search` 那两路就不会查缓存，注脚永远是空的。

飞书里输 `/help` 看命令表，`/clear` 清本会话上下文（那是机器人内存里的历史，不动全局问答缓存）。
单条回复超过 3000 字会截断加一行「答案过长已截断」；同一条飞书消息 id 在 120 秒内只处理一次，
挡的是长连接偶尔重投事件——不挡的话一个问题会收到两个答案。

### 11.6 答案后面那一行注脚

后端在响应头上带了 `X-RAG-Cache` 和 `X-RAG-Sources`（第 1 节的约定表、5.5、5.6），机器人翻成一行小字附在答案末尾：

```
—— 缓存命中 0.8613 · 0 token · 复用的是「文档片段的检索相似度门槛默认是多少？」
```

没命中但检索到了片段时是另一种：`—— 引用 3 段：README.md#2、README.md#7、README.md#11`。
两个头都没有（`/plain` 且这一问没命中缓存）就只回答案，不编造注脚。

### 11.7 演示的两条问题（对应 8.5 那条实测记录）

先用 `/rag` 问「文档片段的检索相似度门槛默认是多少？」，等 3~5 秒（真走模型 + 向量检索）；
再换个说法问「知识库检索的相似度阈值默认是多少？」，半秒内回，注脚写着 `缓存命中 0.8613`。
问句和问句比的是 `CACHE_MIN_SCORE = 0.80`，比「片段和问题」那个检索门槛 0.45（见 8.4）严得多，
所以只有真正同一个问题的另一种问法才会命中。

一个容易看岔的点：机器人不注入角色人设，缓存作用域是 `sha1(模型 + 模式 + 所有 system 文本)`，
所以它落在自己那个桶（`2681e37d80049d80`），浏览器里选「老师」是另一个桶（`1dbd901c70b2c9fa`）。
同一个问题在两边各存一份、各自内部命中，这是设计不是 bug。

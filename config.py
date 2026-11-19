# -*- coding: utf-8 -*-
"""后端配置：只放变量，不放逻辑。API Key 只在这一个文件里，绝不留到前端。
填 Key 两条路任选：设环境变量 DASHSCOPE_API_KEY（推荐，压缩包永远不带 Key），
或把第 9 行末尾那个 "" 换成 Key（README 第一节说的就是这条）。用完去控制台轮换。
"""

import os
# >>> 环境变量优先；想写死就填下面引号里（提交的那份保持空）<<<
API_KEY = os.environ.get("DASHSCOPE_API_KEY") or ""

# 上游服务地址（OpenAI 兼容端点，不带 /chat/completions）
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 默认模型
MODEL = "qwen-plus"

# 监听地址与端口。保持 127.0.0.1 表示只允许本机访问；
# 改成 0.0.0.0 会让同一局域网内的其他设备也能用上你的 Key。
HOST = "127.0.0.1"
PORT = 8000

# ---- 图片生成（阿里云百炼 qwen-image 系列，同步返回结果图）----
# 任务接口根地址
DASHSCOPE_V1 = "https://dashscope.aliyuncs.com/api/v1"
# 文生图 / 图生图都走这个多模态生成端点，且只支持同步调用
IMAGE_ENDPOINT = DASHSCOPE_V1 + "/services/aigc/multimodal-generation/generation"
# 可选模型：qwen-image-2.0 与 qwen-image-2.0-pro 在本账号实测可用
IMAGE_MODELS = ["qwen-image-2.0", "qwen-image-2.0-pro"]
# 默认模型
IMAGE_MODEL = "qwen-image-2.0"
# 出图尺寸。百炼校验的是像素面积：不小于 512x512，不超过 2048x2048，下面每组都实测通过
IMAGE_SIZES = ["1024*1024", "1280*1280", "1328*1328", "1664*928", "928*1664", "1280*720", "720*1280"]
# 单次最多生成几张（模型上限是 6，这里按 4 收口，避免一次烧掉太多额度）
IMAGE_MAX_COUNT = 4

# ---- 角色提示词 / 历史对话的本地文件存储 ----
# 允许写 prompts/<角色>.md 的角色白名单，不在名单里的 id 一律拒绝
ROLE_IDS = ["normal", "teacher", "doctor", "dream", "name", "elysia", "kb"]

# ---- RAG 知识库 ----
# 向量化用的模型。只有百炼的 OpenAI 兼容端点上有这个模型，
# 换 DeepSeek / 智谱 / OpenAI 预设时知识库会报错，对话功能不受影响。
# 实测：批量上限 10 条（超了 HTTP 400），默认 1024 维，dimensions 可传 512/768/1024。
EMBED_MODEL = "text-embedding-v3"
EMBED_DIM = 1024
# 留空表示不传 text_type。百炼原生接口支持 "query"/"document" 非对称检索，
# 兼容端点上没实测过，所以默认不发，避免参数不被接受导致整批失败。
EMBED_TEXT_TYPE = ""
# 切片参数：目标每片多少字、下一块从上一块结尾带回多少字做重叠
RAG_CHUNK_CHARS = 500
RAG_CHUNK_OVERLAP = 80
# 一次问答注入几段资料、相似度低于多少就丢弃（不相关的问题宁可少注入）
# 2026-11-02 用本课程文档实测：真正相关的片段 0.49~0.74，
# 而「今天晚饭吃什么」这种无关问题最高只有 0.41，所以卡在 0.45 能把噪声挡住。
RAG_TOP_K = 4
RAG_MIN_SCORE = 0.45
# 单份文档上限：切片太多会把 kb/*.json 撑得很大，入库也要等逐批向量化
RAG_MAX_DOC_CHARS = 80000
RAG_MAX_CHUNKS = 200
# 检索到的资料是这样拼进 system 消息的，两段都可以自己改
RAG_CONTEXT_HEAD = (
    "【本地知识库资料】下面是从你本机 kb 目录里检索出来的片段，按相关度排序。"
    "回答必须以这些资料为依据，并在引用处标出编号，例如「据[资料2]」。")
RAG_CONTEXT_TAIL = (
    "规则：1) 资料里没有的内容不要编；2) 资料不足时明确说明缺哪部分，"
    "可以补充常识但要标注「以下为通用知识」；3) 中文回答，术语保留原文。")

# ---- 问答缓存（语义缓存，存在 kb/collections/qa.json）----
# 勾了知识库就先查缓存：缓存里最像的问题相似度够高，直接把存好的答案发回去，
# 不再调大模型（省一次生成，0 token）。
# 0.80 是实测标定的，不是拍脑袋：本机拿 text-embedding-v3 对同一话题的不同问法
# 两两算余弦，「检索阈值默认值是多少来着 ↔ 默认阈值是多少」这种改写只有 0.88、
# 「知识库检索的相似度阈值默认是多少？↔ 检索阈值默认值是多少来着」更低到 0.82；
# 而两个不同问题之间最高只到 0.57（「相似度门槛设的多少 ↔ 每片目标字数是多少」）。
# 所以阈值卡在 0.80：命中需要字面接近，宁可漏命中也别答错——缓存答错比没缓存更糟。
CACHE_ENABLED = True
CACHE_MIN_SCORE = 0.80
CACHE_MAX_ENTRIES = 200
CACHE_TTL_SECONDS = 0      # 0 = 不按时间过期，靠删文档 / 改配置来失效
CACHE_COLLECTION = "qa"

# ---- MCP 工具 ----
# 对话页勾上「MCP 天气」后，后端会拉起项目自带的 mcp_server.py 子进程，
# 数据来自 Open-Meteo（免费、无需 Key），所以这一路不用配任何东西。
# 若改用阿里云百炼托管的高德 MCP，端点是
#   https://dashscope.aliyuncs.com/api/v1/mcps/amap-maps/mcp
# 鉴权直接复用上面的 API_KEY（没有第二个 Key），但必须先在控制台点「立即开通」：
#   https://bailian.console.aliyun.com/#/mcp-market

# ---- 飞书机器人（可选，见 feishu_bot.py；没装 lark-oapi 时上面所有功能照常）----
# 飞书开放平台 → 企业自建应用 → 「凭证与基础信息」里拿 App ID（下面那行写死没关系，它不是密钥）。
# App Secret 走环境变量，别写进文件：setx FEISHU_APP_SECRET "你的Secret"（重开终端才生效）。
# !!! 环境变量本来就不在这个文件夹里，所以压缩包永远不带它；泄露嫌疑去后台重置一把即可 !!!
FEISHU_APP_ID = "cli_aa640dcbbe38dc13"
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET") or ""
# 订阅方式选「使用长连接接收事件」时这两个用不上，留着以后改成公网回调 URL 再填。
FEISHU_ENCRYPT_KEY = ""
FEISHU_VERIFY_TOKEN = ""
# bot 用哪个账号登录本机后端（和浏览器走同一条 /api/login，所以 api.py 不用改）。
# 会话 token 只存内存，后端每次重启 bot 会自动重新登录一次。
FEISHU_BACKEND_USER = "mcp_ui_test"
FEISHU_BACKEND_PASSWORD = "Mcp-Test-2026"
# 每个飞书会话往后端带几轮历史（0 = 每次都是单轮，也最省 token）
FEISHU_CONTEXT_TURNS = 6

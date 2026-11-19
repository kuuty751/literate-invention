# -*- coding: utf-8 -*-
"""
MCP 客户端：把 mcp_server.py 提供的工具挂到对话请求上。

流程就是标准的一次 function calling：
  拉起 MCP 服务 → tools/list → 把工具描述塞给模型 →
  模型回 tool_calls → 本地 tools/call → 结果以 role=tool 回填 → 再问一次 → 拿到最终回答

api.py 用 asyncio.run() 在同步请求里调它，所以每次对话起一个 MCP 子进程，
结束后自动回收，不需要常驻端口。
"""
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters, stdio_client

SERVER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")
MAX_ROUNDS = 4


def _params():
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return StdioServerParameters(command=sys.executable, args=[SERVER_PATH], env=env)


def _field(obj, *names):
    """mcp 1.x 用 inputSchema/description，2.x 改成 snake_case，两边都取一次。"""
    for n in names:
        v = getattr(obj, n, None)
        if v is not None:
            return v
    return None


def _to_openai(tools):
    out = []
    for t in tools:
        out.append({
            "type": "function",
            "function": {
                "name": _field(t, "name"),
                "description": _field(t, "description", "title") or "",
                "parameters": _field(t, "inputSchema", "input_schema")
                              or {"type": "object", "properties": {}},
            },
        })
    return out


def _result_text(result):
    parts = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts) or "(工具没有返回文本内容)"


async def _run(messages, chat_fn):
    """chat_fn(messages, tools) → 上游返回的 choice 字典。"""
    async with stdio_client(_params()) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            tools = _to_openai((await session.list_tools()).tools)
            calls = []
            convo = list(messages)
            for _ in range(MAX_ROUNDS):
                choice = await asyncio.to_thread(chat_fn, convo, tools)
                msg = (choice or {}).get("message") or {}
                tcs = msg.get("tool_calls") or []
                if not tcs:
                    return {"content": msg.get("content") or "", "calls": calls,
                            "truncated": bool((choice or {}).get("finish_reason") == "length")}
                convo.append({"role": "assistant", "content": msg.get("content") or "",
                              "tool_calls": tcs})
                for tc in tcs:
                    fn = tc.get("function") or {}
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except ValueError:
                        args = {}
                    result = await session.call_tool(fn.get("name") or "", args)
                    calls.append({"name": fn.get("name"), "args": args})
                    convo.append({"role": "tool", "tool_call_id": tc.get("id"),
                                  "content": _result_text(result)[:8000]})
            return {"content": "工具调用轮次超过 %d 次，已中止。" % MAX_ROUNDS, "calls": calls}


def run(messages, chat_fn):
    """同步入口。返回 {"content": 最终回答, "calls": [{name, args}]}。"""
    return asyncio.run(_run(messages, chat_fn))


def probe():
    """只连一次 MCP 服务把工具名列出来，给 /api/health 用。"""
    async def _probe():
        async with stdio_client(_params()) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                return [t.name for t in (await session.list_tools()).tools]
    return asyncio.run(_probe())

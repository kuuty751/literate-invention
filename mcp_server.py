# -*- coding: utf-8 -*-
"""
本地 MCP 服务：天气查询

  运行：python mcp_server.py            （stdio 传输，被 api.py 自动拉起）
  自测：python mcp_server.py --check 杭州 3   （不起 MCP，直接调工具函数）

数据源用 Open-Meteo，免注册、免密钥，换谁的账号都能跑通。
"""
import sys

import requests

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WX_URL = "https://api.open-meteo.com/v1/forecast"

# WMO 4677 天气现象编码 → 中文
WMO = {
    0: "晴", 1: "大部晴朗", 2: "多云", 3: "阴",
    45: "雾", 48: "雾凇",
    51: "毛毛雨(弱)", 53: "毛毛雨(中)", 55: "毛毛雨(强)",
    56: "冻毛毛雨(弱)", 57: "冻毛毛雨(强)",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨(弱)", 67: "冻雨(强)",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "阵雨(弱)", 81: "阵雨(中)", 82: "阵雨(强)",
    85: "阵雪(弱)", 86: "阵雪(强)",
    95: "雷暴", 96: "雷暴伴小冰雹", 99: "雷暴伴大冰雹",
}

TIMEOUT = (10, 30)


def _describe(code):
    try:
        return WMO.get(int(code), "未知天气(编码 %s)" % code)
    except (TypeError, ValueError):
        return "未知天气"


def _label(top):
    """省/市/区拼起来，但「北京市北京市」这种重复只留一份。"""
    out = []
    for part in (top.get("admin1"), top.get("admin2"), top.get("name")):
        part = (part or "").strip()
        if not part:
            continue
        if any(part.rstrip("市") == kept.rstrip("市") for kept in out):
            continue
        out.append(part)
    return "".join(out) or "该地"


def geocode(city):
    """城市名 → (纬度, 经度, 完整地名)。找不到返回 None。"""
    resp = requests.get(GEO_URL, params={"name": city, "count": 1, "language": "zh",
                                         "format": "json"}, timeout=TIMEOUT)
    resp.raise_for_status()
    results = (resp.json() or {}).get("results") or []
    if not results:
        return None
    top = results[0]
    return top.get("latitude"), top.get("longitude"), _label(top)


def fetch_weather(city, days=1):
    lat, lon, label = geocode(city)
    days = max(1, min(int(days or 1), 7))
    resp = requests.get(WX_URL, params={
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                   "weather_code,wind_speed_10m,precipitation",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                 "precipitation_probability_max,wind_speed_10m_max",
        "timezone": "Asia/Shanghai",
        "forecast_days": days,
    }, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    cur = data.get("current") or {}
    lines = ["【%s】当前（%s）" % (label, cur.get("time", "")),
             "  天气：%s" % _describe(cur.get("weather_code")),
             "  气温：%s℃（体感 %s℃）" % (cur.get("temperature_2m"), cur.get("apparent_temperature")),
             "  湿度：%s%%  风速：%s km/h  降水：%s mm" % (
                 cur.get("relative_humidity_2m"), cur.get("wind_speed_10m"),
                 cur.get("precipitation")),
             "未来 %d 天：" % days]
    day = data.get("daily") or {}
    for i, date in enumerate(day.get("time") or []):
        lines.append("  %s %s，%s~%s℃，降水概率 %s%%，最大风速 %s km/h" % (
            date,
            _describe((day.get("weather_code") or [None] * i)[i]),
            (day.get("temperature_2m_min") or [None] * i)[i],
            (day.get("temperature_2m_max") or [None] * i)[i],
            (day.get("precipitation_probability_max") or [None] * i)[i],
            (day.get("wind_speed_10m_max") or [None] * i)[i]))
    return "\n".join(str(x) for x in lines)


# ---------------- MCP 服务定义 ----------------
try:  # mcp 2.x 把 FastMCP 改名成了 MCPServer
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # pragma: no cover - 兼容 mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

mcp = _Server("weather", instructions="查询中国城市的实时天气与未来几天预报。")


@mcp.tool(description="查询指定城市的实时天气和未来几天预报。city 用中文城市名，"
                      "如「杭州」「北京」；days 为预报天数 1~7，默认 1。")
def get_weather(city: str, days: int = 1) -> str:
    try:
        return fetch_weather(city, days)
    except Exception as exc:  # 把失败也回给模型，让它能解释而不是瞎编
        return "查询失败：%s" % exc


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        print(fetch_weather(sys.argv[2] if len(sys.argv) > 2 else "杭州",
                            sys.argv[3] if len(sys.argv) > 3 else 1))
    else:
        mcp.run(transport="stdio")

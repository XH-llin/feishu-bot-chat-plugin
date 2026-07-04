#!/usr/bin/env python3
"""
MCP Server: Feishu Bot Chat — Hermes 适配版

向 Hermes Agent 暴露 Bot 注册表查询、@ 格式转换等工具。

安装：
  在 ~/.hermes/config.yaml 中添加：

  mcp_servers:
    feishu-bot-chat:
      command: "/path/to/python3"
      args:
        - "/path/to/hermes/mcp_server.py"
      timeout: 60
"""

import json
import asyncio
import sys
import os

# Add parent dir to path so we can import bot_registry
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
import bot_registry


mcp = FastMCP(
    "feishu-bot-chat",
    instructions="""
飞书群聊 Bot 注册表服务。提供以下能力：
1. 列出所有已发现的 Bot（名称、open_id）
2. 查询单个 Bot 信息
3. 将 @botName 文本转换为飞书 <at> 标签格式
4. 刷新 Bot 注册表

使用场景：
- 统筹 Bot 需要 @ 其他 Bot 时，先用 format_at 转换格式
- 检查注册表状态，确认所有 Bot 都在线
- 新加了 Bot profile 后，用 refresh_registry 更新
""",
)


@mcp.tool()
async def list_bots() -> str:
    """列出所有已发现的飞书 Bot（名称、open_id、agent_id）。"""
    try:
        bots = await bot_registry.discover_all_bots()
        result = []
        for agent_id, bot in bots.items():
            result.append({
                "agent_id": agent_id,
                "bot_name": bot.get("botName", "Unknown"),
                "bot_open_id": bot.get("botOpenId", ""),
                "profile_name": bot.get("profile_name", ""),
                "error": bot.get("error", ""),
            })
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def get_bot(identifier: str) -> str:
    """
    按名称或 agent_id 查询单个 Bot 信息。

    Args:
        identifier: Bot 的 agent_id（如 'writer'）或显示名称（如 '正文写作Bot'）
    """
    try:
        bots = await bot_registry.discover_all_bots()
        for agent_id, bot in bots.items():
            if agent_id == identifier or bot.get("botName") == identifier:
                return json.dumps({
                    "agent_id": agent_id,
                    "bot_name": bot.get("botName"),
                    "bot_open_id": bot.get("botOpenId"),
                    "at_tag": bot_registry.format_at_tag(
                        bot.get("botName", ""), bot.get("botOpenId", "")
                    ),
                    "profile_name": bot.get("profile_name"),
                }, ensure_ascii=False, indent=2)
        return json.dumps({"error": f"Bot not found: {identifier}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def format_at(bot_name: str) -> str:
    """
    将 @botName 文本转换为飞书 <at> 标签。

    Args:
        bot_name: Bot 的显示名称（如 '正文写作Bot'）

    Returns:
        飞书 <at user_id="ou_xxx">botName</at> 格式的标签
    """
    try:
        bots = await bot_registry.discover_all_bots()
        for agent_id, bot in bots.items():
            if bot.get("botName") == bot_name:
                tag = bot_registry.format_at_tag(bot_name, bot.get("botOpenId", ""))
                return json.dumps({
                    "bot_name": bot_name,
                    "at_tag": tag,
                    "usage": f"在消息中使用: {tag}",
                }, ensure_ascii=False, indent=2)
        return json.dumps(
            {"error": f"未找到名为 '{bot_name}' 的 Bot。已注册的 Bot: " + ", ".join(
                [b.get("botName", "") for b in bots.values()]
            )},
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def refresh_registry() -> str:
    """强制刷新 Bot 注册表（重新调用飞书 API 发现所有 Bot）。"""
    try:
        bots = await bot_registry.discover_all_bots(force=True)
        return json.dumps({
            "status": "refreshed",
            "bot_count": len(bots),
            "bots": [
                {"name": b.get("botName"), "open_id": b.get("botOpenId")}
                for b in bots.values()
            ],
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def get_registry_status() -> str:
    """查看 Bot 注册表缓存状态（何时发现、几个 Bot、缓存路径）。"""
    try:
        status = bot_registry.get_registry_status()
        return json.dumps(status, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def main():
    mcp.run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
CLI Tool: 发现并缓存所有 Hermes Feishu Bot

用法：
    python3 discover_bots.py          # 使用缓存（24h 内有效）
    python3 discover_bots.py --force  # 强制重新发现
    python3 discover_bots.py --status # 仅查看缓存状态
    python3 discover_bots.py --json   # 输出 JSON 格式

可配合 cron 定期刷新注册表。
"""

import sys
import os
import json
import asyncio
import argparse

# Add parent hermes/ dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot_registry


async def main():
    parser = argparse.ArgumentParser(description="Discover Feishu bots from Hermes profiles")
    parser.add_argument("--force", action="store_true", help="Force re-discovery, ignore cache")
    parser.add_argument("--status", action="store_true", help="Show registry status only")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.status:
        status = bot_registry.get_registry_status()
        if args.json:
            print(json.dumps(status, ensure_ascii=False, indent=2))
        else:
            print(f"状态: {status['status']}")
            print(f"发现时间: {status['discovered_at']}")
            print(f"Bot 数量: {status['bot_count']}")
            if status.get("bot_names"):
                for name in status["bot_names"]:
                    print(f"  - {name}")
            print(f"缓存位置: {status['cache_path']}")
        return

    print("正在发现 Hermes profiles 中的飞书 Bot..." if not args.json else "")
    bots = await bot_registry.discover_all_bots(force=args.force)

    if args.json:
        print(json.dumps(bots, ensure_ascii=False, indent=2))
    else:
        if not bots:
            print("未找到任何飞书 Bot。请检查 ~/.hermes/profiles/*/ 下是否有 .env 文件且包含 FEISHU_APP_ID。")
            return

        print(f"\n发现 {len(bots)} 个 Bot:\n")
        for agent_id, bot in bots.items():
            error = bot.get("error", "")
            status = f" ⚠ {error}" if error else ""
            print(f"  {agent_id}")
            print(f"    名称: {bot.get('botName', 'Unknown')}")
            print(f"    Open ID: {bot.get('botOpenId', 'N/A')}")
            print(f"    Profile: {bot.get('profile_name', '')}{status}")
            print()

        print(f"缓存已保存到: {bot_registry.REGISTRY_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

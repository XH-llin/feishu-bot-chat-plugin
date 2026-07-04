"""
Bot Registry Module — Hermes 适配版

扫描 ~/.hermes/profiles/*/ 发现所有配置了飞书的 profile，
调用飞书 API 获取 Bot 的 open_id 和名称，缓存到共享注册表。

与原版 OpenClaw 的差异：
- 数据源从 openclaw.json bindings 改为扫描 Hermes profiles 目录
- 每个 profile 的 .env 文件提供 FEISHU_APP_ID / FEISHU_APP_SECRET
- 缓存在 ~/.hermes/fbc-registry/registry.json（所有 profile 共享）
"""

import os
import json
import time
from pathlib import Path
from typing import Optional

import httpx


REGISTRY_DIR = Path.home() / ".hermes" / "fbc-registry"
REGISTRY_PATH = REGISTRY_DIR / "registry.json"
CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours


def _load_env_file(env_path: Path) -> dict:
    """Parse a .env file into a dict (simple implementation, no dotenv dependency)."""
    env = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _load_yaml_config(config_path: Path) -> dict:
    """Minimal YAML loader for Hermes config.yaml (no PyYAML dependency)."""
    if not config_path.exists():
        return {}
    # Simple key: value parser for flat structures
    config = {}
    current_section = None
    for line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Check if this is a section header (ends with :)
        if stripped.endswith(":") and not stripped.startswith(" "):
            current_section = stripped[:-1].strip()
            config[current_section] = {}
            continue
        if "=" in stripped and current_section is None:
            key, _, value = stripped.partition("=")
            config[key.strip()] = value.strip()
        elif ":" in stripped and current_section:
            key, _, value = stripped.partition(":")
            config[current_section][key.strip()] = value.strip()
    return config


def discover_profiles() -> list[dict]:
    """
    Scan ~/.hermes/profiles/ for Feishu-configured profiles.

    Returns list of dicts with keys:
        profile_name, app_id, app_secret, domain, agent_id
    """
    profiles_dir = Path.home() / ".hermes" / "profiles"
    if not profiles_dir.exists():
        return []

    profiles = []
    for profile_dir in sorted(profiles_dir.iterdir()):
        if not profile_dir.is_dir():
            continue

        env_path = profile_dir / ".env"
        if not env_path.exists():
            continue

        env = _load_env_file(env_path)
        app_id = env.get("FEISHU_APP_ID", "")
        app_secret = env.get("FEISHU_APP_SECRET", "")
        domain = env.get("FEISHU_DOMAIN", "feishu")

        if not app_id or not app_secret:
            continue

        profiles.append({
            "profile_name": profile_dir.name,
            "agent_id": profile_dir.name,  # In Hermes, agent_id = profile_name
            "app_id": app_id,
            "app_secret": app_secret,
            "domain": domain,
        })

    return profiles


async def get_tenant_token(app_id: str, app_secret: str, domain: str = "feishu") -> str:
    """Get Feishu tenant_access_token."""
    base = "https://open.larksuite.com" if domain == "lark" else "https://open.feishu.cn"
    url = f"{base}/open-apis/auth/v3/tenant_access_token/internal"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            url,
            json={"app_id": app_id, "app_secret": app_secret},
            headers={"Content-Type": "application/json"},
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"tenant_token failed: {data.get('msg', 'unknown error')}")
        return data["tenant_access_token"]


async def get_bot_info(token: str, domain: str = "feishu") -> dict:
    """Get bot open_id and name via bot/v3/info API."""
    base = "https://open.larksuite.com" if domain == "lark" else "https://open.feishu.cn"
    url = f"{base}/open-apis/bot/v3/info"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"bot/v3/info failed: {data.get('msg', 'unknown error')}")
        bot = data.get("bot", {})
        return {
            "bot_open_id": bot.get("open_id", ""),
            "bot_name": bot.get("app_name") or bot.get("bot_name", "Unknown"),
        }


def read_cache() -> Optional[dict]:
    """Read the cached registry if it exists and is valid."""
    try:
        raw = REGISTRY_PATH.read_text(encoding="utf-8")
        cached = json.loads(raw)
        discovered_at = cached.get("discovered_at", "")
        if discovered_at:
            age = time.time() - time.mktime(time.strptime(discovered_at, "%Y-%m-%dT%H:%M:%S"))
            if age < CACHE_TTL_SECONDS:
                return cached
        return None
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return None


def write_cache(bots: dict) -> None:
    """Write bot registry to cache file."""
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "discovered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "bots": bots,
    }
    REGISTRY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def discover_all_bots(force: bool = False) -> dict:
    """
    Discover all Feishu bots from Hermes profiles.

    Returns dict: agent_id -> {accountId, botOpenId, botName, profile_name}
    """
    if not force:
        cached = read_cache()
        if cached and cached.get("bots"):
            return cached["bots"]

    profiles = discover_profiles()
    if not profiles:
        return {}

    bots = {}
    token_cache = {}  # account_id -> token

    for profile in profiles:
        agent_id = profile["agent_id"]
        try:
            # Reuse token for same app_id
            key = profile["app_id"]
            if key not in token_cache:
                token_cache[key] = await get_tenant_token(
                    profile["app_id"], profile["app_secret"], profile["domain"]
                )
            token = token_cache[key]

            info = await get_bot_info(token, profile["domain"])
            bots[agent_id] = {
                "accountId": profile["app_id"],
                "botOpenId": info["bot_open_id"],
                "botName": info["bot_name"],
                "profile_name": profile["profile_name"],
            }
        except Exception as e:
            # Try stale cache as fallback
            cached = read_cache()
            if cached and agent_id in cached.get("bots", {}):
                bots[agent_id] = cached["bots"][agent_id]
            else:
                bots[agent_id] = {
                    "accountId": profile["app_id"],
                    "botOpenId": "",
                    "botName": f"{agent_id} (discovery failed: {e})",
                    "profile_name": profile["profile_name"],
                    "error": str(e),
                }

    if bots:
        write_cache(bots)

    return bots


def format_at_tag(bot_name: str, bot_open_id: str) -> str:
    """Generate a Feishu <at> tag string."""
    return f'<at user_id="{bot_open_id}">{bot_name}</at>'


def get_registry_status() -> dict:
    """Return current registry status."""
    cached = read_cache()
    if not cached:
        return {"status": "empty", "discovered_at": None, "bot_count": 0}
    return {
        "status": "cached",
        "discovered_at": cached.get("discovered_at"),
        "bot_count": len(cached.get("bots", {})),
        "bot_names": [b["botName"] for b in cached.get("bots", {}).values()],
        "cache_path": str(REGISTRY_PATH),
    }

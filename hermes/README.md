# Hermes Agent 适配层

将原 OpenClaw `feishu-bot-chat-plugin` 的核心能力移植到 Hermes Agent 多 Bot 飞书群聊架构。

## 与原版的差异

| 维度 | OpenClaw 原版 | Hermes 适配版 |
|------|-------------|-------------|
| 架构 | 单进程 Gateway，hook 拦截 | 多进程独立 Gateway，MCP + Skill 注入 |
| Bot 发现 | 读 `openclaw.json` bindings | 扫描 `~/.hermes/profiles/*/` |
| 消息过滤 | `inbound_claim` hook | 依赖 SOUL.md 触发规则 |
| @ 格式转换 | `message_sending` hook | Skill 注入 + MCP 工具辅助 |
| 协作规则注入 | `before_prompt_build` hook | 共享 Skill + SOUL.md |
| 缓存 | `~/.openclaw/fbc-registry/` | `~/.hermes/fbc-registry/` |

## 文件结构

```
hermes/
├── README.md                    # 本文档
├── bot_registry.py             # Bot 发现与注册表管理（Python 模块）
├── mcp_server.py               # MCP Server：向 Hermes Agent 暴露 Bot 注册表
├── skills/
│   └── feishu-bot-collaboration/
│       └── SKILL.md            # 群内协作规则 Skill（给 Bot 加载用）
└── scripts/
    └── discover_bots.py        # CLI 工具：手动触发 Bot 发现
```

## 安装

### 1. 安装 Python 依赖

```bash
pip install mcp httpx
```

### 2. 运行一次 Bot 发现

```bash
python3 hermes/scripts/discover_bots.py
```

这会扫描 `~/.hermes/profiles/*/` 下所有配置了飞书的 profile，调用飞书 API 获取每个 Bot 的 `open_id` 和名称，缓存到 `~/.hermes/fbc-registry/registry.json`。

### 3. 配置 MCP Server（可选）

在 `~/.hermes/config.yaml` 中添加：

```yaml
mcp_servers:
  feishu-bot-chat:
    command: "/path/to/python3"
    args:
      - "/path/to/hermes/mcp_server.py"
    timeout: 60
```

然后 `/reset` 重启 Hermes。MCP 工具会以 `mcp_feishu_bot_chat_*` 前缀出现。

### 4. 给每个 Bot 的 SOUL.md 添加协作规则

在每个 profile 的 `SOUL.md` 中追加（或直接加载 skill）：

```markdown
## 群内 Bot 协作规则

加载 skill: `feishu-bot-collaboration`
```

或者直接将 `hermes/skills/feishu-bot-collaboration/SKILL.md` 的内容写进 SOUL.md。

## MCP 工具列表

| 工具名 | 功能 |
|--------|------|
| `list_bots` | 列出所有已发现的 Bot（名称、open_id、agent_id） |
| `get_bot` | 按名称或 agent_id 查询单个 Bot 信息 |
| `format_at` | 将 `@botName` 转为飞书 `<at>` 标签 |
| `refresh_registry` | 强制刷新 Bot 注册表（重新调用飞书 API） |
| `get_registry_status` | 查看注册表缓存状态（何时发现、几个 Bot） |

## 协作规则要点

加载 `feishu-bot-collaboration` skill 后，Bot 会获得以下能力：

1. **知道群内其他 Bot 的 @ 格式** — 使用 `<at user_id="ou_xxx">名字</at>` 而非 `@名字`
2. **任务型 @ vs 通知型 @** — 任务型需回传结果，通知型加 🔕仅通知 标记
3. **回传规则** — 处理完任务后 @ 回发起者，但不要循环 @
4. **默认不主动 @** — 只有用户触发协作关键字或明确要求时才 @ 其他 Bot

## 前置条件

与原版相同：每个参与协作的 Bot 应用需要在飞书开发者后台开通：

**`im:message.group_at_msg.include_bot:readonly`**（接收群聊中机器人 @机器人的消息）

路径：开发者后台 → 应用 → 权限管理 → 搜索上述权限 → 开通 → 发布

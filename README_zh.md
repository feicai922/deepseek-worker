# DeepSeek Worker（Antigravity 插件）

[English](./README.md) | [简体中文](./README_zh.md)

一个面向 [Antigravity](https://antigravity.google) 的本地插件，让 Gemini 可以通过 MCP（Model Context Protocol）把**大文件/日志总结、样板代码生成、单元测试编写、注释翻译、批量文件处理**等杂活派发给 **DeepSeek** 或任意 **OpenAI 兼容接口**，从而大幅减少 Gemini 的上下文与额度消耗。

---

## 核心特性

- **本地直读文件（省输入 Token）**：调用 `deepseek_run_task` 或 `deepseek_batch_files` 时直接传入 `file_paths`，由 MCP 服务端在本地读取文件内容后发给 DeepSeek，无需先把大文件塞进 Gemini 的上下文。
- **结果直接落盘（省输出 Token）**：传入 `output_path` 可让 DeepSeek 生成的测试、文档或脚本直接写入磁盘，仅向 Gemini 返回简短预览与行数统计。
- **多文件并发批处理**：通过 `deepseek_batch_files` 并发对多个文件执行摘要、排查或结构化提取。
- **原生交互式前端面板（MCP App）**：支持从 Antigravity 左侧边栏、右侧 `+` 菜单或对话中直接打开设置面板，提供：
  - **Base URL 配置**（内置 DeepSeek 官方、OpenAI `/v1`、Ollama 本地预设及自定义中转地址）
  - **API Key 安全保存**（通过 `app`-only 工具写入本地 `worker_config.json`，**原始密钥不会进入 Gemini 对话上下文**）
  - **一键拉取可用模型**（请求 `/models` 接口并生成下拉框与快捷选择标签）
  - **连通性测试**（实测响应耗时、实际模型名称与返回内容）
  - **Token 用量热力图**（本地记录每日与各模型输入/输出 Token 消耗，展示仿 GitHub 近半年/近一年贡献热力图）
- **内置分流 Skill 与 Rule**：自带 `SKILL.md` 和 `AGENTS.md`，引导 Gemini 自动识别适合交给 DeepSeek 的任务并在完成后复核验证。

---

## 环境要求

- [Antigravity](https://antigravity.google)（App / IDE / CLI）
- [`uv`](https://docs.astral.sh/uv/)（Python 包与虚拟环境管理工具）

> **说明：** 普通使用者**不需要**安装 Node.js，前端单文件页面（`ui/dist/app.html`）已预打包包含在仓库中。

---

## 安装方法

1. 将本仓库克隆到 Antigravity 的全局插件目录：

   **Windows (PowerShell)：**
   ```powershell
   git clone https://github.com/feicai922/deepseek-worker.git "$env:USERPROFILE\.gemini\config\plugins\deepseek-worker"
   ```

   **macOS / Linux：**
   ```bash
   git clone https://github.com/feicai922/deepseek-worker.git ~/.gemini/config/plugins/deepseek-worker
   ```

2. *（可选）* 预先同步 Python 依赖（不执行也可，首次启动时 `uv run` 会自动安装）：
   ```bash
   uv --directory ~/.gemini/config/plugins/deepseek-worker sync
   ```

3. 新开一个 Antigravity 对话（或在 **Additional Options (...) > MCP Servers** 中刷新/重启 `deepseek-worker` 服务）即可使用。

---

## 配置方式

### 方式一：通过可视化前端配置（推荐）
1. 在 Antigravity 左侧边栏、右侧辅助栏 `+` 菜单打开 **DeepSeek Worker**，或在对话中告诉 Gemini：
   > 「打开 DeepSeek Worker 设置」
2. 填写 **Base URL** 与 **API Key**。
3. 点击 **获取可用模型** 拉取模型列表并点选（或手动填写，如 `deepseek-chat`、`deepseek-reasoner`）。
4. 点击 **保存配置**，再点击 **测试连通性** 确认接口正常。

### 方式二：手动编辑配置文件
在插件目录下将 `worker_config.example.json` 复制为 `worker_config.json` 并填写：

```json
{
  "api_key": "sk-你的密钥",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-chat",
  "timeout_seconds": 120,
  "max_file_bytes": 200000
}
```

每次工具调用都会动态读取配置文件，修改后立即生效，无需重启 Antigravity。也支持通过环境变量 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL` 作为回退配置。

---

## 暴露的 MCP 工具

| 工具名 | 可见性 | 说明 |
| :--- | :--- | :--- |
| `deepseek_open_settings` | 模型 + UI | 打开交互式 DeepSeek Worker 设置面板。 |
| `deepseek_run_task` | 模型 | 派发单个子任务，支持直接读取 `file_paths` 和写入 `output_path`。 |
| `deepseek_batch_files` | 模型 | 并发处理多个本地文件（`max_concurrency` 1–8）。 |
| `deepseek_check_config` | 模型 | 检查脱敏后的配置状态并可选测试连通性。 |
| `deepseek_usage_stats` | 模型 | 汇总已记录的 Token 用量（今日、近 7 天、近 30 天、累计及分模型统计）。 |
| `app_get_config` / `app_save_config` / `app_fetch_models` / `app_test_connection` / `app_get_usage` / `app_reset_usage` | 仅前端 UI | 仅供面板调用的内部工具，不向模型暴露密钥。 |

---

## 使用示例

配置完成后，直接在任意工作区用自然语言对 Gemini 下达指令即可：
- 「让 DeepSeek 帮我总结 `logs/server.log` 里的主要报错原因」
- 「让 DeepSeek 并发扫描这 5 个文件，列出缺少异常处理的地方」
- 「让 DeepSeek 给 `src/parser.py` 写一份 pytest 单元测试并保存到 `tests/test_parser.py`，然后你运行测试帮我验证」

---

## 目录结构

```text
deepseek-worker/
├── plugin.json                  # Antigravity 插件清单
├── mcp_config.json              # 基于 uv 与 ${PLUGIN_ROOT} 的跨平台 Stdio MCP 配置
├── pyproject.toml               # Python 依赖声明（mcp、openai）
├── server.py                    # MCP 服务端与工具实现
├── worker_config.example.json   # 配置示例模板（本地使用时保存为 worker_config.json）
├── rules/
│   └── AGENTS.md                # 自动分流杂活给 DeepSeek 的全局规则
├── skills/
│   └── deepseek-delegation/
│       └── SKILL.md             # 委派任务工作流 Skill
└── ui/
    ├── package.json             # @modelcontextprotocol/ext-apps 与 esbuild
    ├── template.html            # 适配宿主亮/暗主题的页面模板
    ├── src/app.ts               # 基于 MCP Apps SDK 的前端交互逻辑
    ├── build.mjs                # 打包并内联 JS 为单文件 ui/dist/app.html
    └── dist/app.html            # 预构建的单文件前端产物
```

---

## 二次开发（修改前端 UI）

如果修改了 `ui/template.html` 或 `ui/src/app.ts`，重新构建单文件 HTML：

```bash
cd ui
npm install
node build.mjs
```

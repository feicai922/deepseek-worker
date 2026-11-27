# DeepSeek Worker for Antigravity

[English](./README.md) | [简体中文](./README_zh.md)

An [Antigravity](https://antigravity.google) plugin that enables Gemini to delegate routine engineering subtasks—large file/log summarization, boilerplate generation, unit tests, docstrings, translations, and parallel batch file analysis—to **DeepSeek** or any **OpenAI-compatible API** via the Model Context Protocol (MCP), significantly reducing Gemini token and quota usage.

---

## Features

- **Direct Disk Reads (Save Input Tokens)**: Pass `file_paths` directly to `deepseek_run_task` or `deepseek_batch_files`. The MCP server reads files locally on disk and forwards them to DeepSeek without loading huge files into Gemini's context window.
- **Direct Disk Writes (Save Output Tokens)**: Pass `output_path` to `deepseek_run_task` to write generated tests, docs, or boilerplate straight to disk and return only a concise preview to Gemini.
- **Parallel Batch Processing**: Process multiple files concurrently with `deepseek_batch_files`.
- **Interactive MCP App Settings UI**: Built-in Antigravity UI panel (accessible from the left sidebar, the side pane `+` menu, or in chat via `deepseek_open_settings`) to configure:
  - **Base URL** (with presets for DeepSeek Official, OpenAI `/v1`, local Ollama, or custom proxies)
  - **API Key** (stored locally in `worker_config.json` via `app`-only tools; never exposed to Gemini's model context)
  - **Live Model Discovery** (`/models` endpoint query with dropdown & quick-select chips)
  - **Connectivity Test** (measures latency and verifies model response)
  - **Token Usage Heatmap** (tracks local daily/model token usage and renders a GitHub-style 6-month / 1-year contribution heatmap)
- **Built-in Delegation Skill & Rule**: Bundles `skills/deepseek-delegation/SKILL.md` and `rules/AGENTS.md` so Gemini automatically recognizes when to offload grunt work.

---

## Requirements

- [Antigravity](https://antigravity.google) (App / IDE / CLI)
- [`uv`](https://docs.astral.sh/uv/) (Python package & environment runner)

> **Note:** End users do **not** need Node.js. The single-file MCP App frontend (`ui/dist/app.html`) is pre-built and included in this repository.

---

## Installation

1. Clone this repository into Antigravity's global plugins directory:

   **macOS / Linux:**
   ```bash
   git clone https://github.com/feicai922/deepseek-worker.git ~/.gemini/config/plugins/deepseek-worker
   ```

   **Windows (PowerShell):**
   ```powershell
   git clone https://github.com/feicai922/deepseek-worker.git "$env:USERPROFILE\.gemini\config\plugins\deepseek-worker"
   ```

2. *(Optional)* Pre-sync the Python environment (otherwise `uv run` installs dependencies automatically on first launch):
   ```bash
   uv --directory ~/.gemini/config/plugins/deepseek-worker sync
   ```

3. Open a new Antigravity conversation (or restart the MCP server under **Additional Options (...) > MCP Servers**).

---

## Configuration

### Option A: Using the Interactive UI (Recommended)
1. Open **DeepSeek Worker** from the Antigravity left sidebar, the side pane `+` menu, or ask Gemini:
   > *"Open DeepSeek Worker settings"*
2. Enter your **Base URL** and **API Key**.
3. Click **Fetch Models** (`获取可用模型`) to populate available models, or type a model name manually (e.g. `deepseek-chat`, `deepseek-reasoner`).
4. Click **Save** (`保存配置`), then **Test Connection** (`测试连通性`).

### Option B: Manual File Configuration
Copy `worker_config.example.json` to `worker_config.json` inside the plugin directory:

```json
{
  "api_key": "sk-your-api-key",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-chat",
  "timeout_seconds": 120,
  "max_file_bytes": 200000
}
```

Configuration is loaded dynamically on every tool call—changes take effect immediately without restarting Antigravity. You may also set `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and `DEEPSEEK_MODEL` environment variables as fallbacks.

---

## MCP Tools

| Tool | Visibility | Description |
| :--- | :--- | :--- |
| `deepseek_open_settings` | Model + UI | Opens the interactive DeepSeek Worker settings panel. |
| `deepseek_run_task` | Model | Delegates a single task; supports `file_paths` and `output_path`. |
| `deepseek_batch_files` | Model | Processes multiple local files in parallel (`max_concurrency` 1–8). |
| `deepseek_check_config` | Model | Reports masked config status and optionally tests connectivity. |
| `deepseek_usage_stats` | Model | Summarizes recorded token usage (today, 7d, 30d, all-time, per-model). |
| `app_get_config` / `app_save_config` / `app_fetch_models` / `app_test_connection` / `app_get_usage` / `app_reset_usage` | App-only | Internal UI callbacks hidden from the model to keep secrets out of context. |

---

## Usage Examples

Once configured, talk to Gemini naturally in any workspace:
- *"Have DeepSeek summarize the errors in `logs/server.log`."*
- *"Use DeepSeek to audit these 5 files in parallel and list any missing error handling."*
- *"Ask DeepSeek to draft pytest unit tests for `src/parser.py` and save them to `tests/test_parser.py`, then run the tests to verify."*

---

## Project Structure

```text
deepseek-worker/
├── plugin.json                  # Antigravity plugin manifest
├── mcp_config.json              # Stdio MCP launcher using uv + ${PLUGIN_ROOT}
├── pyproject.toml               # Python dependencies (mcp, openai)
├── server.py                    # FastMCP / MCPServer implementation & tools
├── worker_config.example.json   # Template config (copy to worker_config.json)
├── rules/
│   └── AGENTS.md                # Always-on rule guiding delegation to DeepSeek
├── skills/
│   └── deepseek-delegation/
│       └── SKILL.md             # Delegation workflow skill
└── ui/
    ├── package.json             # @modelcontextprotocol/ext-apps + esbuild
    ├── template.html            # Single-file HTML template & theme-aware styles
    ├── src/app.ts               # Frontend logic using MCP Apps SDK
    ├── build.mjs                # Bundles & inlines JS into ui/dist/app.html
    └── dist/app.html            # Pre-built self-contained UI artifact
```

---

## Development

To modify and rebuild the frontend UI:

```bash
cd ui
npm install
node build.mjs
```

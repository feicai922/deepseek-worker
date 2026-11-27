"""MCP server that lets Antigravity delegate grunt work to DeepSeek / OpenAI-compatible APIs."""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent
from openai import AsyncOpenAI

PLUGIN_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PLUGIN_DIR / "worker_config.json"
USAGE_PATH = PLUGIN_DIR / "usage_stats.json"
APP_HTML_PATH = PLUGIN_DIR / "ui" / "dist" / "app.html"
APP_URI = "ui://deepseek-worker/settings.html"
_USAGE_LOCK = asyncio.Lock()

DEFAULT_SYSTEM_PROMPT = (
    "You are a fast, precise engineering worker delegated a subtask by a lead agent. "
    "Follow the instruction strictly, avoid fluff, and output ready-to-use results."
)

SETTINGS_UI_META: dict[str, Any] = {
    "ui": {"resourceUri": APP_URI},
    "com.google.antigravity/ui": {
        "entrypoints": [
            {"type": "aux_pane", "title": "DeepSeek Worker"},
            {"type": "global", "title": "DeepSeek Worker"},
        ]
    },
}
APP_ONLY_META: dict[str, Any] = {"ui": {"visibility": ["app"]}}

mcp = MCPServer("deepseek-worker")


@dataclass(frozen=True)
class WorkerConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float
    max_file_bytes: int


def normalize_base_url(raw_url: str) -> str:
    """Normalize an OpenAI-compatible base URL for AsyncOpenAI."""
    url = raw_url.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    return url or "https://api.deepseek.com"


def load_config() -> WorkerConfig:
    """Load configuration from worker_config.json with env-var fallbacks."""
    data: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    api_key = str(data.get("api_key") or os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    raw_base_url = str(
        data.get("base_url") or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
    )
    model = str(data.get("model") or os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat").strip()
    timeout_seconds = float(data.get("timeout_seconds") or 120)
    max_file_bytes = int(data.get("max_file_bytes") or 200_000)

    return WorkerConfig(
        api_key=api_key,
        base_url=normalize_base_url(raw_base_url),
        model=model or "deepseek-chat",
        timeout_seconds=timeout_seconds,
        max_file_bytes=max_file_bytes,
    )


def mask_secret(secret: str) -> str:
    if not secret:
        return "(not set)"
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-4:]}"


def public_config_payload(cfg: WorkerConfig) -> dict[str, Any]:
    """Return UI-safe config metadata without exposing the raw API key."""
    return {
        "has_api_key": bool(cfg.api_key),
        "api_key_masked": mask_secret(cfg.api_key),
        "base_url": cfg.base_url,
        "model": cfg.model,
        "timeout_seconds": cfg.timeout_seconds,
        "max_file_bytes": cfg.max_file_bytes,
        "config_path": str(CONFIG_PATH),
    }


def resolve_effective_config(
    api_key: str = "",
    base_url: str = "",
    model: str = "",
) -> WorkerConfig:
    """Merge transient UI inputs over persisted worker_config.json settings."""
    saved = load_config()
    return WorkerConfig(
        api_key=api_key.strip() or saved.api_key,
        base_url=normalize_base_url(base_url) if base_url.strip() else saved.base_url,
        model=model.strip() or saved.model,
        timeout_seconds=saved.timeout_seconds,
        max_file_bytes=saved.max_file_bytes,
    )


def read_files_context(file_paths: list[str], max_file_bytes: int) -> tuple[str, list[str]]:
    """Read local files from disk so the lead agent does not burn tokens reading them first."""
    sections: list[str] = []
    warnings: list[str] = []

    for raw_path in file_paths:
        path = Path(raw_path).expanduser()
        if not path.exists():
            warnings.append(f"Missing file: {raw_path}")
            continue
        if path.is_dir():
            warnings.append(f"Skipped directory (pass explicit file paths): {raw_path}")
            continue

        try:
            raw_bytes = path.read_bytes()
        except Exception as exc:
            warnings.append(f"Failed reading {raw_path}: {exc}")
            continue

        truncated = False
        if len(raw_bytes) > max_file_bytes:
            raw_bytes = raw_bytes[:max_file_bytes]
            truncated = True

        text = raw_bytes.decode("utf-8", errors="replace")
        note = " [TRUNCATED]" if truncated else ""
        sections.append(f"### File: {path}{note}\n```\n{text}\n```")

    return "\n\n".join(sections), warnings


async def call_llm(
    cfg: WorkerConfig,
    user_prompt: str,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float = 0.2,
) -> tuple[str, str]:
    """Execute a single chat completion call and return (text, usage_summary)."""
    if not cfg.api_key:
        raise ValueError(
            f"DeepSeek API key is not configured yet. Open DeepSeek Worker settings or edit {CONFIG_PATH}."
        )

    client = AsyncOpenAI(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        timeout=cfg.timeout_seconds,
    )
    target_model = (model or cfg.model).strip()
    messages = [
        {"role": "system", "content": system_prompt or DEFAULT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    kwargs: dict[str, Any] = {
        "model": target_model,
        "messages": messages,
    }
    if "reasoner" not in target_model.lower():
        kwargs["temperature"] = temperature

    resp = await client.chat.completions.create(**kwargs)
    choice = resp.choices[0].message
    content = (choice.content or "").strip()
    if not content:
        reasoning = getattr(choice, "reasoning_content", None)
        if reasoning:
            content = str(reasoning).strip()

    usage = resp.usage
    used_model = resp.model or target_model
    if usage:
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens))
        usage_summary = (
            f"model={used_model}, "
            f"prompt_tokens={prompt_tokens}, "
            f"completion_tokens={completion_tokens}"
        )
    else:
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        usage_summary = f"model={used_model}"

    await record_usage(used_model, prompt_tokens, completion_tokens, total_tokens)
    return content, usage_summary


def _empty_usage_store() -> dict[str, Any]:
    return {"daily": {}, "models": {}, "updated_at": ""}


def _read_usage_store_sync() -> dict[str, Any]:
    if not USAGE_PATH.exists():
        return _empty_usage_store()
    try:
        raw = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {
                "daily": raw.get("daily") if isinstance(raw.get("daily"), dict) else {},
                "models": raw.get("models") if isinstance(raw.get("models"), dict) else {},
                "updated_at": str(raw.get("updated_at") or ""),
            }
    except Exception:
        pass
    return _empty_usage_store()


def _accumulate_bucket(
    bucket_map: dict[str, Any],
    key: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
) -> None:
    cur = bucket_map.get(key)
    if not isinstance(cur, dict):
        cur = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    cur["calls"] = int(cur.get("calls", 0)) + 1
    cur["prompt_tokens"] = int(cur.get("prompt_tokens", 0)) + prompt_tokens
    cur["completion_tokens"] = int(cur.get("completion_tokens", 0)) + completion_tokens
    cur["total_tokens"] = int(cur.get("total_tokens", 0)) + total_tokens
    bucket_map[key] = cur


async def record_usage(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
) -> None:
    """Persist per-day and per-model token usage safely under an async lock."""
    today_key = date.today().isoformat()
    async with _USAGE_LOCK:
        store = _read_usage_store_sync()
        _accumulate_bucket(store["daily"], today_key, prompt_tokens, completion_tokens, total_tokens)
        _accumulate_bucket(
            store["models"], model_name or "unknown", prompt_tokens, completion_tokens, total_tokens
        )
        store["updated_at"] = datetime.now().isoformat(timespec="seconds")
        USAGE_PATH.write_text(json.dumps(store, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sum_range(daily: dict[str, Any], start_day: date | None, end_day: date) -> dict[str, int]:
    totals = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for day_str, stats in daily.items():
        if not isinstance(stats, dict):
            continue
        try:
            d = date.fromisoformat(day_str)
        except ValueError:
            continue
        if d > end_day or (start_day is not None and d < start_day):
            continue
        totals["calls"] += int(stats.get("calls", 0))
        totals["prompt_tokens"] += int(stats.get("prompt_tokens", 0))
        totals["completion_tokens"] += int(stats.get("completion_tokens", 0))
        totals["total_tokens"] += int(stats.get("total_tokens", 0))
    return totals


def _compute_streak(daily: dict[str, Any], today: date) -> int:
    def is_active(d: date) -> bool:
        entry = daily.get(d.isoformat())
        return isinstance(entry, dict) and int(entry.get("calls", 0)) > 0

    cursor = today if is_active(today) else today - timedelta(days=1)
    streak = 0
    while is_active(cursor):
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def build_usage_payload(weeks: int = 26) -> dict[str, Any]:
    """Build aggregated KPIs and daily map for the GitHub-style heatmap."""
    weeks_clamped = max(4, min(int(weeks or 26), 53))
    store = _read_usage_store_sync()
    daily: dict[str, Any] = store["daily"]
    today = date.today()

    # Align window start to Sunday so columns line up cleanly (GitHub contribution grid).
    days_since_sunday = (today.weekday() + 1) % 7
    grid_start = today - timedelta(days=days_since_sunday + (weeks_clamped - 1) * 7)

    grid_daily: dict[str, dict[str, int]] = {}
    for day_str, stats in daily.items():
        if not isinstance(stats, dict):
            continue
        try:
            d = date.fromisoformat(day_str)
        except ValueError:
            continue
        if grid_start <= d <= today:
            grid_daily[day_str] = {
                "calls": int(stats.get("calls", 0)),
                "prompt_tokens": int(stats.get("prompt_tokens", 0)),
                "completion_tokens": int(stats.get("completion_tokens", 0)),
                "total_tokens": int(stats.get("total_tokens", 0)),
            }

    models_list = [
        {
            "model": name,
            "calls": int(s.get("calls", 0)),
            "prompt_tokens": int(s.get("prompt_tokens", 0)),
            "completion_tokens": int(s.get("completion_tokens", 0)),
            "total_tokens": int(s.get("total_tokens", 0)),
        }
        for name, s in store["models"].items()
        if isinstance(s, dict)
    ]
    models_list.sort(key=lambda x: x["total_tokens"], reverse=True)

    active_days = sum(
        1 for s in daily.values() if isinstance(s, dict) and int(s.get("calls", 0)) > 0
    )

    return {
        "weeks": weeks_clamped,
        "grid_start": grid_start.isoformat(),
        "today_date": today.isoformat(),
        "today": _sum_range(daily, today, today),
        "last_7d": _sum_range(daily, today - timedelta(days=6), today),
        "last_30d": _sum_range(daily, today - timedelta(days=29), today),
        "total": _sum_range(daily, None, today),
        "active_days": active_days,
        "streak_days": _compute_streak(daily, today),
        "daily": grid_daily,
        "models": models_list,
        "updated_at": store.get("updated_at", ""),
    }


@mcp.resource(
    APP_URI,
    name="DeepSeek Worker Settings",
    mime_type="text/html;profile=mcp-app",
    meta={"ui": {"prefersBorder": False}},
)
def settings_app_html() -> str:
    """Serve the bundled single-file MCP App UI."""
    if not APP_HTML_PATH.exists():
        return "<html><body><p>UI bundle missing. Run node ui/build.mjs.</p></body></html>"
    return APP_HTML_PATH.read_text(encoding="utf-8")


@mcp.tool(title="Open DeepSeek Worker Settings", meta=SETTINGS_UI_META)
async def deepseek_open_settings() -> CallToolResult:
    """Open the interactive DeepSeek Worker UI to configure API key, base URL, model, fetch models, and test connectivity."""
    cfg = load_config()
    payload = public_config_payload(cfg)
    summary = (
        f"Opened DeepSeek Worker settings UI "
        f"(base_url={cfg.base_url}, model={cfg.model}, api_key={'configured' if cfg.api_key else 'not set'})."
    )
    return CallToolResult(
        content=[TextContent(type="text", text=summary)],
        structuredContent=payload,
    )


@mcp.tool(meta=APP_ONLY_META)
async def app_get_config() -> CallToolResult:
    """App-only: return current masked configuration for the settings UI."""
    payload = public_config_payload(load_config())
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        structuredContent=payload,
    )


@mcp.tool(meta=APP_ONLY_META)
async def app_save_config(
    api_key: str = "",
    clear_api_key: bool = False,
    base_url: str = "",
    model: str = "",
    timeout_seconds: float = 120,
    max_file_bytes: int = 200_000,
) -> CallToolResult:
    """App-only: persist user settings to worker_config.json without exposing secrets to the model."""
    existing = load_config()
    if clear_api_key:
        next_key = ""
    elif api_key.strip():
        next_key = api_key.strip()
    else:
        next_key = existing.api_key

    data = {
        "api_key": next_key,
        "base_url": normalize_base_url(base_url) if base_url.strip() else existing.base_url,
        "model": model.strip() or existing.model,
        "timeout_seconds": max(5.0, float(timeout_seconds or existing.timeout_seconds)),
        "max_file_bytes": max(1000, int(max_file_bytes or existing.max_file_bytes)),
    }
    CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    payload = public_config_payload(load_config())
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        structuredContent=payload,
    )


@mcp.tool(meta=APP_ONLY_META)
async def app_fetch_models(api_key: str = "", base_url: str = "") -> CallToolResult:
    """App-only: query /models on the configured OpenAI-compatible endpoint."""
    cfg = resolve_effective_config(api_key=api_key, base_url=base_url)
    if not cfg.api_key:
        payload: dict[str, Any] = {"ok": False, "error": "请先填写 API Key。"}
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(payload))],
            structuredContent=payload,
        )

    client = AsyncOpenAI(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        timeout=min(cfg.timeout_seconds, 30.0),
    )
    try:
        page = await client.models.list()
        models = sorted({m.id for m in page.data if getattr(m, "id", None)})
        payload = {"ok": True, "models": models}
    except Exception as exc:
        payload = {"ok": False, "error": str(exc)}

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        structuredContent=payload,
    )


@mcp.tool(meta=APP_ONLY_META)
async def app_test_connection(api_key: str = "", base_url: str = "", model: str = "") -> CallToolResult:
    """App-only: run a lightweight ping completion to verify API connectivity."""
    cfg = resolve_effective_config(api_key=api_key, base_url=base_url, model=model)
    started = time.perf_counter()
    try:
        reply, usage = await call_llm(
            cfg,
            user_prompt="Reply with exactly: OK",
            system_prompt="Reply concisely.",
            model=cfg.model,
            temperature=0.0,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        payload: dict[str, Any] = {
            "ok": True,
            "message": f"连接成功 ({elapsed_ms} ms)\n{usage}\n响应: {reply}",
        }
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        payload = {
            "ok": False,
            "message": f"连接失败 ({elapsed_ms} ms): {exc}",
        }

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        structuredContent=payload,
    )


@mcp.tool(meta=APP_ONLY_META)
async def app_get_usage(weeks: int = 26) -> CallToolResult:
    """App-only: return aggregated token usage and daily heatmap data."""
    payload = build_usage_payload(weeks=weeks)
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        structuredContent=payload,
    )


@mcp.tool(meta=APP_ONLY_META)
async def app_reset_usage() -> CallToolResult:
    """App-only: clear recorded token usage statistics."""
    async with _USAGE_LOCK:
        USAGE_PATH.write_text(
            json.dumps(_empty_usage_store(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    payload = build_usage_payload(weeks=26)
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        structuredContent=payload,
    )


@mcp.tool()
async def deepseek_usage_stats() -> str:
    """Summarize recorded DeepSeek Worker token usage (today, 7d, 30d, all-time, and per-model)."""
    u = build_usage_payload(weeks=52)
    lines = [
        f"Today ({u['today_date']}): {u['today']['total_tokens']:,} tokens ({u['today']['calls']} calls)",
        f"Last 7 days: {u['last_7d']['total_tokens']:,} tokens ({u['last_7d']['calls']} calls)",
        f"Last 30 days: {u['last_30d']['total_tokens']:,} tokens ({u['last_30d']['calls']} calls)",
        (
            f"All-time: {u['total']['total_tokens']:,} tokens "
            f"(prompt={u['total']['prompt_tokens']:,}, completion={u['total']['completion_tokens']:,}, "
            f"calls={u['total']['calls']}, active_days={u['active_days']}, streak={u['streak_days']}d)"
        ),
    ]
    if u["models"]:
        lines.append("By model:")
        for m in u["models"]:
            lines.append(
                f"- {m['model']}: {m['total_tokens']:,} tokens ({m['calls']} calls)"
            )
    return "\n".join(lines)


@mcp.tool()
async def deepseek_check_config(test_connection: bool = False) -> str:
    """Check DeepSeek Worker configuration status and optionally verify API connectivity.

    Args:
        test_connection: Set true to send a minimal test request to the configured API.
    """
    cfg = load_config()
    lines = [
        f"Config file: {CONFIG_PATH}",
        f"API key: {mask_secret(cfg.api_key)}",
        f"Base URL: {cfg.base_url}",
        f"Default model: {cfg.model}",
        f"Timeout: {cfg.timeout_seconds}s, Max file bytes: {cfg.max_file_bytes}",
    ]
    if not cfg.api_key:
        lines.append(
            "Status: NOT CONFIGURED. Call deepseek_open_settings to open the UI or edit worker_config.json."
        )
        return "\n".join(lines)

    if test_connection:
        try:
            reply, usage = await call_llm(
                cfg,
                user_prompt="Reply with exactly: OK",
                system_prompt="Reply concisely.",
                temperature=0.0,
            )
            lines.append(f"Connection test: SUCCESS ({usage}) -> {reply}")
        except Exception as exc:
            lines.append(f"Connection test: FAILED -> {exc}")

    return "\n".join(lines)


@mcp.tool()
async def deepseek_run_task(
    instruction: str,
    file_paths: list[str] | None = None,
    output_path: str | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float = 0.2,
) -> str:
    """Delegate a subtask (summarization, boilerplate, tests, docs, translation, analysis) to DeepSeek.

    Reads any provided `file_paths` directly from disk inside the MCP server so the lead agent saves tokens.
    If `output_path` is provided, writes DeepSeek's response directly to that file and returns a short summary.

    Args:
        instruction: Clear task description for DeepSeek.
        file_paths: Optional list of local file paths for DeepSeek to read directly.
        output_path: Optional file path to save DeepSeek's output directly on disk.
        system_prompt: Optional custom system prompt.
        model: Optional model override (defaults to worker_config.json model).
        temperature: Sampling temperature (default 0.2).
    """
    cfg = load_config()
    prompt_parts = [f"## Task\n{instruction.strip()}"]
    warnings: list[str] = []

    if file_paths:
        files_text, warnings = read_files_context(file_paths, cfg.max_file_bytes)
        if files_text:
            prompt_parts.append(f"## Input Files\n{files_text}")

    full_prompt = "\n\n".join(prompt_parts)
    try:
        result, usage = await call_llm(
            cfg,
            user_prompt=full_prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
        )
    except Exception as exc:
        warning_block = ("\nWarnings:\n- " + "\n- ".join(warnings)) if warnings else ""
        return f"DeepSeek task failed: {exc}{warning_block}"

    warning_prefix = ("Warnings:\n- " + "\n- ".join(warnings) + "\n\n") if warnings else ""

    if output_path:
        dest = Path(output_path).expanduser()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(result + ("\n" if not result.endswith("\n") else ""), encoding="utf-8")
        line_count = len(result.splitlines())
        preview_lines = "\n".join(result.splitlines()[:12])
        return (
            f"{warning_prefix}Saved DeepSeek output to `{dest}` "
            f"({line_count} lines, {len(result)} chars; {usage}).\n\n"
            f"Preview (first 12 lines):\n{preview_lines}"
        )

    return f"{warning_prefix}[{usage}]\n\n{result}"


@mcp.tool()
async def deepseek_batch_files(
    instruction: str,
    file_paths: list[str],
    model: str | None = None,
    max_concurrency: int = 4,
) -> str:
    """Apply the same instruction to multiple local files in parallel using DeepSeek.

    Ideal for summarizing, reviewing, translating, or extracting structured notes across many files
    without loading all of them into Gemini's context.

    Args:
        instruction: Task to run on each file independently.
        file_paths: List of local file paths to process.
        model: Optional model override.
        max_concurrency: Maximum parallel API requests (1-8, default 4).
    """
    if not file_paths:
        return "No file_paths provided."

    cfg = load_config()
    if not cfg.api_key:
        return (
            f"DeepSeek API key is not configured yet. Call deepseek_open_settings or edit {CONFIG_PATH}."
        )

    limit = max(1, min(max_concurrency, 8))
    sem = asyncio.Semaphore(limit)

    async def process_one(raw_path: str) -> str:
        async with sem:
            files_text, warnings = read_files_context([raw_path], cfg.max_file_bytes)
            if not files_text:
                reason = "; ".join(warnings) if warnings else "Could not read file."
                return f"## {raw_path}\nError: {reason}"
            prompt = f"## Task\n{instruction.strip()}\n\n{files_text}"
            try:
                result, usage = await call_llm(cfg, user_prompt=prompt, model=model)
                warn = f" ({'; '.join(warnings)})" if warnings else ""
                return f"## {raw_path} [{usage}]{warn}\n{result}"
            except Exception as exc:
                return f"## {raw_path}\nError: {exc}"

    results = await asyncio.gather(*(process_one(p) for p in file_paths))
    return "\n\n---\n\n".join(results)


if __name__ == "__main__":
    mcp.run(transport="stdio")

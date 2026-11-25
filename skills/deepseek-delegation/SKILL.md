---
name: deepseek-delegation
description: Delegate grunt work, large file/log summarization, boilerplate code, unit tests, docstrings, translations, and batch file processing to DeepSeek via the deepseek-worker MCP tools to save Gemini context and quota.
---

# Delegating Grunt Work to DeepSeek (`deepseek-worker`)

Use the `deepseek-worker` MCP tools (`deepseek_run_task`, `deepseek_batch_files`, `deepseek_check_config`) whenever a task can be offloaded cleanly to DeepSeek so Gemini focuses on planning, complex reasoning, editing, and verification.

## Best Tasks to Delegate
- **Large file or log summarization**: Pass `file_paths` directly to `deepseek_run_task` instead of reading huge files into Gemini's context first.
- **Batch multi-file analysis**: Use `deepseek_batch_files` to summarize, audit, or extract info from many files in parallel.
- **Boilerplate & repetitive generation**: Draft unit tests, docstrings, type annotations, mock data, CRUD scaffolding, commit messages, or translations.
- **Drafting to disk**: When generating a long standalone file (e.g., tests, docs, scripts), pass `output_path` so DeepSeek writes straight to disk and Gemini only reviews a concise preview or runs tests against it.

## How to Delegate Effectively
1. Give **clear, self-contained instructions** with exact output format expectations.
2. Prefer passing `file_paths` directly rather than pasting file contents into the instruction.
3. Always **verify** DeepSeek's output (run tests, lint, or review diffs) before claiming completion.
4. If DeepSeek fails because the API key is missing, call `deepseek_open_settings` so the user can fill in the API key, base URL, and model directly in the interactive settings UI (or edit `C:\Users\33889\.gemini\config\plugins\deepseek-worker\worker_config.json`).

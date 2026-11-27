# DeepSeek Worker Delegation (Enabled by Default)

When the `deepseek-worker` MCP server is available (`deepseek_run_task`, `deepseek_batch_files`), **proactively delegate grunt work to DeepSeek by default** without waiting for the user to ask explicitly, in order to save Gemini context and quota.

- Default delegation targets: summarizing large files/logs (pass `file_paths` directly so Gemini avoids loading large files), batch multi-file analysis (`deepseek_batch_files`), drafting boilerplate, unit tests, docstrings, translations, and standalone docs/scripts (use `output_path` when writing long outputs directly to disk).
- Gemini stays responsible for planning, complex reasoning, editing decisions, and verifying DeepSeek's output (e.g., running tests/linters) before reporting completion.

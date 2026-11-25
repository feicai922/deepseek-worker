# DeepSeek Worker Delegation

When the `deepseek-worker` MCP server is configured and the user asks to offload grunt work (or when summarizing large logs/files, processing many files in batch, translating, or drafting boilerplate/tests/docs), prefer delegating those subtasks via `deepseek_run_task` or `deepseek_batch_files` (passing `file_paths` directly to avoid loading large files into Gemini context), then review and verify the results.

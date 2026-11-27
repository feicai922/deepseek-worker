import {
  App,
  applyDocumentTheme,
  applyHostStyleVariables,
} from "@modelcontextprotocol/ext-apps";

interface ConfigPayload {
  has_api_key: boolean;
  api_key_masked: string;
  base_url: string;
  model: string;
  timeout_seconds: number;
  max_file_bytes: number;
  config_path?: string;
}

interface ModelsPayload {
  ok: boolean;
  models?: string[];
  error?: string;
}

interface TestPayload {
  ok: boolean;
  message: string;
}

interface UsageBucket {
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

interface ModelUsage extends UsageBucket {
  model: string;
}

interface UsagePayload {
  weeks: number;
  grid_start: string;
  today_date: string;
  today: UsageBucket;
  last_7d: UsageBucket;
  last_30d: UsageBucket;
  total: UsageBucket;
  active_days: number;
  streak_days: number;
  daily: Record<string, UsageBucket>;
  models: ModelUsage[];
  updated_at: string;
}

const el = {
  badge: document.getElementById("config-badge") as HTMLSpanElement,
  baseUrl: document.getElementById("base-url") as HTMLInputElement,
  apiKey: document.getElementById("api-key") as HTMLInputElement,
  keyStatus: document.getElementById("key-status") as HTMLSpanElement,
  toggleKey: document.getElementById("toggle-key") as HTMLButtonElement,
  clearKey: document.getElementById("clear-key") as HTMLButtonElement,
  model: document.getElementById("model") as HTMLInputElement,
  fetchModels: document.getElementById("fetch-models") as HTMLButtonElement,
  modelsBox: document.getElementById("models-box") as HTMLDivElement,
  modelsCount: document.getElementById("models-count") as HTMLSpanElement,
  modelsSelect: document.getElementById("models-select") as HTMLSelectElement,
  modelsChips: document.getElementById("models-chips") as HTMLDivElement,
  timeoutSeconds: document.getElementById("timeout-seconds") as HTMLInputElement,
  maxFileBytes: document.getElementById("max-file-bytes") as HTMLInputElement,
  saveBtn: document.getElementById("save-btn") as HTMLButtonElement,
  testBtn: document.getElementById("test-btn") as HTMLButtonElement,
  refreshBtn: document.getElementById("refresh-btn") as HTMLButtonElement,
  statusBox: document.getElementById("status-box") as HTMLDivElement,
  usageSubtitle: document.getElementById("usage-subtitle") as HTMLParagraphElement,
  refreshUsageBtn: document.getElementById("refresh-usage-btn") as HTMLButtonElement,
  resetUsageBtn: document.getElementById("reset-usage-btn") as HTMLButtonElement,
  kpiToday: document.getElementById("kpi-today") as HTMLDivElement,
  kpiTodayCalls: document.getElementById("kpi-today-calls") as HTMLDivElement,
  kpi7d: document.getElementById("kpi-7d") as HTMLDivElement,
  kpi7dCalls: document.getElementById("kpi-7d-calls") as HTMLDivElement,
  kpi30d: document.getElementById("kpi-30d") as HTMLDivElement,
  kpi30dCalls: document.getElementById("kpi-30d-calls") as HTMLDivElement,
  kpiTotal: document.getElementById("kpi-total") as HTMLDivElement,
  kpiStreak: document.getElementById("kpi-streak") as HTMLDivElement,
  heatmapMonths: document.getElementById("heatmap-months") as HTMLDivElement,
  heatmapGrid: document.getElementById("heatmap-grid") as HTMLDivElement,
  heatmapDetail: document.getElementById("heatmap-detail") as HTMLSpanElement,
  modelPills: document.getElementById("model-pills") as HTMLDivElement,
};

let clearApiKeyFlag = false;
let currentHasKey = false;
let currentWeeks = 26;
let resetConfirmTimer: number | null = null;

function showStatus(kind: "ok" | "err" | "info", msg: string) {
  el.statusBox.className = "status-box visible" + (kind === "info" ? "" : ` ${kind}`);
  el.statusBox.textContent = msg;
}

function applyConfig(cfg: ConfigPayload) {
  currentHasKey = Boolean(cfg.has_api_key);
  clearApiKeyFlag = false;
  el.baseUrl.value = cfg.base_url || "https://api.deepseek.com";
  el.model.value = cfg.model || "deepseek-chat";
  el.timeoutSeconds.value = String(cfg.timeout_seconds ?? 120);
  el.maxFileBytes.value = String(cfg.max_file_bytes ?? 200000);
  el.apiKey.value = "";

  if (cfg.has_api_key) {
    el.badge.className = "badge ok";
    el.badge.textContent = "已配置";
    el.keyStatus.textContent = `已保存: ${cfg.api_key_masked}`;
    el.apiKey.placeholder = `已保存 ${cfg.api_key_masked}（留空则保持不变）`;
  } else {
    el.badge.className = "badge warn";
    el.badge.textContent = "未配置 Key";
    el.keyStatus.textContent = "未设置";
    el.apiKey.placeholder = "请输入 API Key (例如 sk-...)";
  }
}

function renderModels(models: string[]) {
  el.modelsBox.classList.add("visible");
  el.modelsCount.textContent = `获取到 ${models.length} 个可用模型`;
  el.modelsSelect.innerHTML = "";
  el.modelsChips.innerHTML = "";

  const currentModel = el.model.value.trim();
  for (const id of models) {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = id;
    if (id === currentModel) opt.selected = true;
    el.modelsSelect.appendChild(opt);

    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip" + (id === currentModel ? " active" : "");
    chip.textContent = id;
    chip.addEventListener("click", () => {
      el.model.value = id;
      highlightSelectedModel(id);
    });
    el.modelsChips.appendChild(chip);
  }
}

function highlightSelectedModel(modelId: string) {
  el.modelsSelect.value = modelId;
  for (const btn of Array.from(el.modelsChips.querySelectorAll("button.chip"))) {
    btn.classList.toggle("active", btn.textContent === modelId);
  }
}

function setBusy(busy: boolean) {
  el.saveBtn.disabled = busy;
  el.testBtn.disabled = busy;
  el.fetchModels.disabled = busy;
  el.refreshBtn.disabled = busy;
}

function extractStructured<T>(res: { structuredContent?: unknown; content?: Array<{ type: string; text?: string }> }): T | null {
  if (res.structuredContent && typeof res.structuredContent === "object") {
    return res.structuredContent as T;
  }
  const textPart = res.content?.find((c) => c.type === "text" && c.text)?.text;
  if (textPart) {
    try {
      return JSON.parse(textPart) as T;
    } catch {
      return null;
    }
  }
  return null;
}

const app = new App({ name: "DeepSeek Worker", version: "0.1.0" }, {});

app.ontoolresult = (result) => {
  const data = extractStructured<ConfigPayload>(result as never);
  if (data && typeof data.base_url === "string") {
    applyConfig(data);
  }
};

app.onhostcontextchanged = (ctx) => {
  if (ctx.theme) applyDocumentTheme(ctx.theme);
  if (ctx.styles?.variables) applyHostStyleVariables(ctx.styles.variables);
};

async function reloadFromServer() {
  setBusy(true);
  try {
    const res = await app.callServerTool({ name: "app_get_config", arguments: {} });
    const data = extractStructured<ConfigPayload>(res as never);
    if (data) applyConfig(data);
  } catch (err) {
    showStatus("err", `读取配置失败: ${String(err)}`);
  } finally {
    setBusy(false);
  }
}

async function saveConfig(): Promise<boolean> {
  setBusy(true);
  showStatus("info", "正在保存配置...");
  try {
    const res = await app.callServerTool({
      name: "app_save_config",
      arguments: {
        api_key: el.apiKey.value.trim(),
        clear_api_key: clearApiKeyFlag,
        base_url: el.baseUrl.value.trim(),
        model: el.model.value.trim(),
        timeout_seconds: Number(el.timeoutSeconds.value) || 120,
        max_file_bytes: Number(el.maxFileBytes.value) || 200000,
      },
    });
    const data = extractStructured<ConfigPayload>(res as never);
    if (data) {
      applyConfig(data);
      showStatus("ok", `配置已保存到 ${data.config_path ?? "worker_config.json"}，立即生效（无需重启）。`);
      return true;
    }
    showStatus("err", "保存失败：未收到服务端确认。");
    return false;
  } catch (err) {
    showStatus("err", `保存失败: ${String(err)}`);
    return false;
  } finally {
    setBusy(false);
  }
}

async function fetchModels() {
  if (!el.apiKey.value.trim() && !currentHasKey) {
    showStatus("err", "请先填写 API Key，再获取可用模型列表。");
    return;
  }
  setBusy(true);
  showStatus("info", "正在请求 /models 获取可用模型...");
  try {
    const res = await app.callServerTool({
      name: "app_fetch_models",
      arguments: {
        api_key: el.apiKey.value.trim(),
        base_url: el.baseUrl.value.trim(),
      },
    });
    const data = extractStructured<ModelsPayload>(res as never);
    if (data?.ok && data.models && data.models.length > 0) {
      renderModels(data.models);
      showStatus("ok", `成功获取 ${data.models.length} 个模型，点击上方模型名即可选用，别忘了点“保存配置”。`);
    } else if (data?.ok) {
      showStatus("info", "接口连接成功，但返回的模型列表为空，请手动填写模型名。");
    } else {
      showStatus("err", `获取模型失败: ${data?.error ?? "未知错误"}`);
    }
  } catch (err) {
    showStatus("err", `获取模型失败: ${String(err)}`);
  } finally {
    setBusy(false);
  }
}

async function testConnection() {
  if (!el.apiKey.value.trim() && !currentHasKey) {
    showStatus("err", "请先填写 API Key，再测试连通性。");
    return;
  }
  setBusy(true);
  showStatus("info", "正在发送测试请求...");
  try {
    const res = await app.callServerTool({
      name: "app_test_connection",
      arguments: {
        api_key: el.apiKey.value.trim(),
        base_url: el.baseUrl.value.trim(),
        model: el.model.value.trim(),
      },
    });
    const data = extractStructured<TestPayload>(res as never);
    if (data?.ok) {
      el.badge.className = "badge ok";
      el.badge.textContent = "测试通过";
      showStatus("ok", data.message);
      void loadUsageStats(currentWeeks);
    } else {
      el.badge.className = "badge err";
      el.badge.textContent = "连接失败";
      showStatus("err", data?.message ?? "测试失败");
    }
  } catch (err) {
    el.badge.className = "badge err";
    el.badge.textContent = "连接失败";
    showStatus("err", `测试失败: ${String(err)}`);
  } finally {
    setBusy(false);
  }
}

el.toggleKey.addEventListener("click", () => {
  const isPwd = el.apiKey.type === "password";
  el.apiKey.type = isPwd ? "text" : "password";
  el.toggleKey.textContent = isPwd ? "隐藏" : "显示";
});

el.clearKey.addEventListener("click", () => {
  el.apiKey.value = "";
  clearApiKeyFlag = true;
  currentHasKey = false;
  el.keyStatus.textContent = "待保存（将清除原 Key）";
  el.apiKey.placeholder = "已标记清除，点击保存后生效";
});

for (const btn of Array.from(document.querySelectorAll<HTMLButtonElement>(".presets .chip"))) {
  btn.addEventListener("click", () => {
    const url = btn.dataset.url;
    const model = btn.dataset.model;
    if (url) el.baseUrl.value = url;
    if (model) el.model.value = model;
  });
}

el.modelsSelect.addEventListener("change", () => {
  el.model.value = el.modelsSelect.value;
  highlightSelectedModel(el.modelsSelect.value);
});

el.model.addEventListener("input", () => {
  highlightSelectedModel(el.model.value.trim());
});

function formatCompactTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 10_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString("en-US");
}

function parseIsoDateUtc(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function toIsoDateUtc(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function computeHeatLevel(tokens: number, scaleMax: number): number {
  if (tokens <= 0) return 0;
  const ratio = tokens / scaleMax;
  if (ratio <= 0.25) return 1;
  if (ratio <= 0.5) return 2;
  if (ratio <= 0.75) return 3;
  return 4;
}

function formatDayDetail(dateStr: string, stats?: UsageBucket): string {
  if (!stats || stats.calls === 0) {
    return `${dateStr}：0 tokens（无调用）`;
  }
  return `${dateStr}：${stats.total_tokens.toLocaleString("en-US")} tokens（输入 ${stats.prompt_tokens.toLocaleString("en-US")} / 输出 ${stats.completion_tokens.toLocaleString("en-US")} · ${stats.calls} 次调用）`;
}

function renderUsage(u: UsagePayload) {
  el.kpiToday.textContent = formatCompactTokens(u.today.total_tokens);
  el.kpiToday.title = `${u.today.total_tokens.toLocaleString("en-US")} tokens`;
  el.kpiTodayCalls.textContent = `${u.today.calls} 次调用`;

  el.kpi7d.textContent = formatCompactTokens(u.last_7d.total_tokens);
  el.kpi7d.title = `${u.last_7d.total_tokens.toLocaleString("en-US")} tokens`;
  el.kpi7dCalls.textContent = `${u.last_7d.calls} 次调用`;

  el.kpi30d.textContent = formatCompactTokens(u.last_30d.total_tokens);
  el.kpi30d.title = `${u.last_30d.total_tokens.toLocaleString("en-US")} tokens`;
  el.kpi30dCalls.textContent = `${u.last_30d.calls} 次调用`;

  el.kpiTotal.textContent = formatCompactTokens(u.total.total_tokens);
  el.kpiTotal.title = `${u.total.total_tokens.toLocaleString("en-US")} tokens`;
  el.kpiStreak.textContent = `连续 ${u.streak_days} 天 · 活跃 ${u.active_days} 天`;

  if (u.updated_at) {
    el.usageSubtitle.textContent = `最近更新: ${u.updated_at.replace("T", " ")}`;
  } else {
    el.usageSubtitle.textContent = "按本地实际调用统计输入与输出 Token";
  }

  let maxDailyTokens = 0;
  for (const s of Object.values(u.daily)) {
    if (s.total_tokens > maxDailyTokens) maxDailyTokens = s.total_tokens;
  }
  const scaleMax = Math.max(maxDailyTokens, 4000);

  const startDate = parseIsoDateUtc(u.grid_start);
  const todayDate = parseIsoDateUtc(u.today_date);

  el.heatmapGrid.innerHTML = "";
  el.heatmapMonths.innerHTML = "";
  el.heatmapMonths.style.gridTemplateColumns = `repeat(${u.weeks}, 11px)`;

  let prevMonth = -1;
  for (let w = 0; w < u.weeks; w++) {
    const colStart = new Date(startDate.getTime() + w * 7 * 86_400_000);
    const monthCell = document.createElement("span");
    monthCell.className = "heatmap-month-label";
    const m = colStart.getUTCMonth() + 1;
    if (w === 0 || m !== prevMonth) {
      monthCell.textContent = `${m}月`;
      prevMonth = m;
    }
    el.heatmapMonths.appendChild(monthCell);

    for (let dow = 0; dow < 7; dow++) {
      const cellDate = new Date(colStart.getTime() + dow * 86_400_000);
      const cell = document.createElement("button");
      cell.type = "button";
      if (cellDate.getTime() > todayDate.getTime()) {
        cell.className = "heat-cell future";
        cell.tabIndex = -1;
      } else {
        const iso = toIsoDateUtc(cellDate);
        const stats = u.daily[iso];
        const tokens = stats?.total_tokens ?? 0;
        const level = computeHeatLevel(tokens, scaleMax);
        const detail = formatDayDetail(iso, stats);
        cell.className = "heat-cell";
        cell.dataset.level = String(level);
        cell.title = detail;
        cell.setAttribute("aria-label", detail);
        cell.addEventListener("mouseenter", () => {
          el.heatmapDetail.textContent = detail;
        });
        cell.addEventListener("focus", () => {
          el.heatmapDetail.textContent = detail;
        });
        cell.addEventListener("click", () => {
          el.heatmapDetail.textContent = detail;
        });
      }
      el.heatmapGrid.appendChild(cell);
    }
  }

  el.heatmapDetail.textContent = formatDayDetail(u.today_date, u.daily[u.today_date]);

  el.modelPills.innerHTML = "";
  for (const m of u.models) {
    const pill = document.createElement("span");
    pill.className = "model-pill";
    const strong = document.createElement("strong");
    strong.textContent = m.model;
    pill.appendChild(strong);
    pill.appendChild(
      document.createTextNode(` · ${formatCompactTokens(m.total_tokens)} (${m.calls}次)`),
    );
    el.modelPills.appendChild(pill);
  }
}

async function loadUsageStats(weeks: number = currentWeeks) {
  currentWeeks = weeks;
  for (const btn of Array.from(document.querySelectorAll<HTMLButtonElement>("[data-weeks]"))) {
    btn.classList.toggle("active", Number(btn.dataset.weeks) === weeks);
  }
  try {
    const res = await app.callServerTool({
      name: "app_get_usage",
      arguments: { weeks },
    });
    const data = extractStructured<UsagePayload>(res as never);
    if (data && typeof data.grid_start === "string") {
      renderUsage(data);
    }
  } catch (err) {
    el.heatmapDetail.textContent = `加载用量统计失败: ${String(err)}`;
  }
}

async function handleResetUsage() {
  if (el.resetUsageBtn.dataset.confirm !== "1") {
    el.resetUsageBtn.dataset.confirm = "1";
    el.resetUsageBtn.textContent = "确认清空?";
    if (resetConfirmTimer !== null) window.clearTimeout(resetConfirmTimer);
    resetConfirmTimer = window.setTimeout(() => {
      delete el.resetUsageBtn.dataset.confirm;
      el.resetUsageBtn.textContent = "清空";
      resetConfirmTimer = null;
    }, 3000);
    return;
  }
  if (resetConfirmTimer !== null) {
    window.clearTimeout(resetConfirmTimer);
    resetConfirmTimer = null;
  }
  delete el.resetUsageBtn.dataset.confirm;
  el.resetUsageBtn.textContent = "清空";
  try {
    const res = await app.callServerTool({ name: "app_reset_usage", arguments: {} });
    const data = extractStructured<UsagePayload>(res as never);
    if (data) renderUsage(data);
  } catch (err) {
    el.heatmapDetail.textContent = `清空失败: ${String(err)}`;
  }
}

for (const btn of Array.from(document.querySelectorAll<HTMLButtonElement>("[data-weeks]"))) {
  btn.addEventListener("click", () => {
    const w = Number(btn.dataset.weeks) || 26;
    void loadUsageStats(w);
  });
}

el.refreshUsageBtn.addEventListener("click", () => void loadUsageStats(currentWeeks));
el.resetUsageBtn.addEventListener("click", () => void handleResetUsage());

el.saveBtn.addEventListener("click", () => void saveConfig());
el.testBtn.addEventListener("click", () => void testConnection());
el.fetchModels.addEventListener("click", () => void fetchModels());
el.refreshBtn.addEventListener("click", () => void reloadFromServer());

(async () => {
  await app.connect();
  const ctx = app.getHostContext();
  if (ctx?.theme) applyDocumentTheme(ctx.theme);
  if (ctx?.styles?.variables) applyHostStyleVariables(ctx.styles.variables);
  await Promise.all([reloadFromServer(), loadUsageStats(currentWeeks)]);
})();

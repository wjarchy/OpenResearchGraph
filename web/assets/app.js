const form = document.querySelector("#research-form");
const submitButton = document.querySelector("#submit-button");
const eventList = document.querySelector("#event-list");
const runStatus = document.querySelector("#run-status");
const runIdLabel = document.querySelector("#run-id");
const reportElement = document.querySelector("#report");
const copyButton = document.querySelector("#copy-report");
const canvas = document.querySelector("#trend-chart");
const chartNote = document.querySelector("#chart-note");
let currentReport = "";
let currentRunId = "";

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value;
  return node.innerHTML;
}

function markdownToHtml(markdown) {
  const lines = markdown.split("\n");
  let listOpen = false;
  const html = [];
  for (const line of lines) {
    if (line.startsWith("- ")) {
      if (!listOpen) { html.push("<ul>"); listOpen = true; }
      html.push(`<li>${escapeHtml(line.slice(2)).replace(/`([^`]+)`/g, "<code>$1</code>")}</li>`);
      continue;
    }
    if (listOpen) { html.push("</ul>"); listOpen = false; }
    if (line.startsWith("# ")) html.push(`<h1>${escapeHtml(line.slice(2))}</h1>`);
    else if (line.startsWith("## ")) html.push(`<h2>${escapeHtml(line.slice(3))}</h2>`);
    else if (line.trim()) html.push(`<p>${escapeHtml(line)}</p>`);
  }
  if (listOpen) html.push("</ul>");
  return html.join("");
}

function setStatus(label, className) {
  runStatus.textContent = label;
  runStatus.className = `status ${className}`;
}

function resetWorkspace() {
  eventList.innerHTML = "";
  currentReport = "";
  reportElement.innerHTML = '<p class="placeholder">正在等待 Scribe 汇总报告。</p>';
  copyButton.disabled = true;
  document.querySelectorAll(".agent-card").forEach((card) => card.classList.remove("active", "done"));
  clearChart();
}

function addEvent(event) {
  const item = document.createElement("li");
  const time = new Date(event.created_at || Date.now()).toLocaleTimeString("zh-CN", { hour12: false });
  item.innerHTML = `<time>${time}</time>${escapeHtml(event.message || event.kind)}`;
  eventList.append(item);
  eventList.scrollTop = eventList.scrollHeight;
}

function updateAgent(role, state) {
  if (!role) return;
  const card = document.querySelector(`[data-role="${role}"]`);
  if (!card) return;
  card.classList.toggle("active", state === "active");
  card.classList.toggle("done", state === "done");
}

function clearChart() {
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.strokeStyle = "rgba(211,239,228,.10)";
  for (let y = 50; y < canvas.height; y += 62) {
    context.beginPath(); context.moveTo(48, y); context.lineTo(canvas.width - 20, y); context.stroke();
  }
  chartNote.textContent = "Agent 完成数据分析后显示合成数据趋势。";
}

function drawChart(data) {
  if (!data?.length) return;
  const context = canvas.getContext("2d");
  clearChart();
  const grouped = data.reduce((groups, point) => {
    (groups[point.series] ||= []).push(point);
    return groups;
  }, {});
  const colors = ["#65e2ad", "#f5c36a", "#88a7ff"];
  const values = data.map((point) => Number(point.y));
  const max = Math.max(...values) * 1.15;
  const left = 52, right = canvas.width - 35, top = 28, bottom = canvas.height - 44;
  Object.entries(grouped).forEach(([sector, points], index) => {
    context.strokeStyle = colors[index % colors.length];
    context.fillStyle = colors[index % colors.length];
    context.lineWidth = 3;
    context.beginPath();
    points.forEach((point, pointIndex) => {
      const x = left + (pointIndex / Math.max(1, points.length - 1)) * (right - left);
      const y = bottom - (Number(point.y) / max) * (bottom - top);
      pointIndex ? context.lineTo(x, y) : context.moveTo(x, y);
      context.fillRect(x - 3, y - 3, 6, 6);
      context.font = "12px DM Mono";
      context.fillText(String(point.x).slice(0, 8), x - 22, bottom + 24);
    });
    context.stroke();
    context.font = "12px DM Mono";
    context.fillText(sector, left + index * 180, 17);
  });
  chartNote.textContent = "合成演示数据 · 单位 GWh · 不代表真实市场规模";
}

async function loadFinalState(runId) {
  const response = await fetch(`/api/research/${runId}`);
  if (!response.ok) return;
  const state = await response.json();
  currentRunId = runId;
  runIdLabel.textContent = runId.slice(0, 12);
  document.querySelectorAll(".agent-card").forEach((card) => {
    const completed = state.completed_nodes?.includes(card.dataset.role);
    card.classList.toggle("done", Boolean(completed));
    card.classList.remove("active");
  });
  setStatus(
    state.status === "completed" ? "已完成" : state.status === "failed" ? "失败 · 可续跑" : "执行中",
    state.status === "completed" ? "completed" : state.status === "failed" ? "failed" : "running",
  );
  currentReport = state.report || "";
  reportElement.innerHTML = currentReport ? markdownToHtml(currentReport) : '<p class="placeholder">未生成报告。</p>';
  copyButton.disabled = !currentReport;
  drawChart(state.analyses?.[0]?.chart_spec?.data || []);
}

async function loadRecentRuns() {
  const container = document.querySelector("#recent-runs");
  try {
    const response = await fetch("/api/research?limit=5");
    const runs = response.ok ? await response.json() : [];
    container.innerHTML = "";
    if (!runs.length) {
      container.innerHTML = '<span class="placeholder">暂无历史</span>';
      return;
    }
    for (const run of runs) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${run.status} · ${run.query}`;
      button.title = run.query;
      button.addEventListener("click", () => loadFinalState(run.run_id));
      container.append(button);
    }
  } catch {
    container.innerHTML = '<span class="placeholder">历史暂不可用</span>';
  }
}

function processFrame(frame, runId) {
  const eventLine = frame.split("\n").find((line) => line.startsWith("event:"));
  const dataLine = frame.split("\n").find((line) => line.startsWith("data:"));
  if (!dataLine) return;
  const kind = eventLine?.slice(6).trim() || "message";
  const event = JSON.parse(dataLine.slice(5).trim());
  if (kind === "run.queued" || kind === "run.started") setStatus("执行中", "running");
  if (kind === "agent.started") updateAgent(event.role, "active");
  if (kind === "agent.completed") updateAgent(event.role, "done");
  if (kind === "run.completed") {
    setStatus("已完成", "completed");
    loadFinalState(runId);
  }
  if (kind === "run.failed") setStatus("失败 · 可续跑", "failed");
  if (event.message) addEvent(event);
}

form.addEventListener("submit", async (submitEvent) => {
  submitEvent.preventDefault();
  resetWorkspace();
  submitButton.disabled = true;
  setStatus("排队中", "running");
  const query = document.querySelector("#query").value.trim();
  try {
    const response = await fetch("/api/research/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ query, session_id: "web-demo" }),
    });
    if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let runId = "";
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";
      for (const frame of frames) {
        if (frame.includes("event: run.accepted")) {
          const data = JSON.parse(frame.split("data:")[1].trim());
          runId = data.run_id;
          currentRunId = runId;
          runIdLabel.textContent = runId.slice(0, 12);
        } else processFrame(frame, runId);
      }
      if (done) break;
    }
  } catch (error) {
    setStatus("连接失败", "failed");
    addEvent({ message: `客户端错误：${error.message}` });
  } finally {
    submitButton.disabled = false;
    loadRecentRuns();
  }
});

copyButton.addEventListener("click", async () => {
  await navigator.clipboard.writeText(currentReport);
  copyButton.textContent = "已复制";
  setTimeout(() => { copyButton.textContent = "复制 Markdown"; }, 1500);
});

clearChart();
loadRecentRuns();

fetch("/api/health").then((response) => response.json()).then((data) => {
  document.querySelector("#mode-label").textContent = data.provider === "remote" ? "远程模型模式" : "确定性演示模式";
}).catch(() => {});

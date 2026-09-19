/* 冷链装箱温控规划器前端逻辑(无第三方依赖) */
"use strict";

const $ = (id) => document.getElementById(id);

/* ---------------- 示例数据(分段运输) ---------------- */
const SAMPLE = {
  transport_hours: 24,
  box_capacity: 12,
  max_boxes: 20,
  volume_unit: "m³",
  use_segments: true,
  // 单一温区模式(未勾选分段时使用)
  zones: [
    { name: "深冷区", t_min: -30, t_max: -18 },
    { name: "冷冻区", t_min: -18, t_max: -2 },
    { name: "冷藏区", t_min: 0, t_max: 8 },
    { name: "常温区", t_min: 15, t_max: 25 },
  ],
  // 分段运输:各段时长之和 14 + 6 + 4 = 24h
  segments: [
    {
      name: "干线冷链",
      hours: 14,
      zones: [
        { name: "深冷区", t_min: -30, t_max: -18 },
        { name: "冷冻区", t_min: -18, t_max: -2 },
        { name: "冷藏区", t_min: 0, t_max: 8 },
      ],
    },
    {
      name: "支线转运",
      hours: 6,
      zones: [
        { name: "冷冻区", t_min: -18, t_max: -2 },
        { name: "冷藏区", t_min: 0, t_max: 8 },
      ],
    },
    {
      name: "末端配送",
      hours: 4,
      zones: [
        { name: "冷藏区", t_min: 0, t_max: 8 },
        { name: "常温区", t_min: 15, t_max: 25 },
      ],
    },
  ],
  cargoes: [
    { name: "三文鱼刺身", units: 18, unit_volume: 0.4, t_min: -2, t_max: 2, max_transport_hours: 36 },
    { name: "巴氏鲜奶", units: 40, unit_volume: 0.25, t_min: 2, t_max: 6, max_transport_hours: "" },
    { name: "冷冻牛排", units: 30, unit_volume: 0.8, t_min: -22, t_max: -15, max_transport_hours: "" },
    { name: "冰淇淋", units: 24, unit_volume: 0.5, t_min: -28, t_max: -18, max_transport_hours: 48 },
    { name: "冷冻饺子", units: 26, unit_volume: 0.6, t_min: -18, t_max: -5, max_transport_hours: "" },
    { name: "鲜切水果", units: 20, unit_volume: 0.3, t_min: 2, t_max: 8, max_transport_hours: 20 },
    { name: "温控疫苗", units: 12, unit_volume: 0.15, t_min: 2, t_max: 8, max_transport_hours: 12 },
    { name: "巧克力", units: 30, unit_volume: 0.2, t_min: 15, t_max: 22, max_transport_hours: "" },
    { name: "热带水果(温区缺失)", units: 10, unit_volume: 0.4, t_min: 10, t_max: 14, max_transport_hours: "" },
  ],
};

/* ---------------- 动态行 ---------------- */
function addRow(tbody, cells) {
  const tr = document.createElement("tr");
  cells.forEach((html) => {
    const td = document.createElement("td");
    td.innerHTML = html;
    tr.appendChild(td);
  });
  tbody.appendChild(tr);
  tr.querySelector("input")?.focus();
  return tr;
}

const zoneCell = (v = "", ph = "", type = "text") =>
  `<input type="${type}" value="${v ?? ""}" placeholder="${ph}" ${type === "number" ? 'step="any"' : ""} />`;

function addZoneRow(z = {}, tbody = $("zoneRows")) {
  addRow(tbody, [
    zoneCell(z.name, "如 冷藏区"),
    zoneCell(z.t_min ?? "", "-18", "number"),
    zoneCell(z.t_max ?? "", "8", "number"),
    '<button type="button" class="btn btn-del">删除</button>',
  ]);
}

/* ---------------- 运输段卡片 ---------------- */
function addSegmentCard(seg = {}) {
  const list = $("segmentList");
  const card = document.createElement("div");
  card.className = "segment-card";
  card.innerHTML = `
    <div class="segment-head">
      <span class="seg-no"></span>
      <input class="seg-name" type="text" value="${seg.name ?? ""}" placeholder="段名称,如 干线冷链" />
      <label class="seg-hours-label">时长 h
        <input class="seg-hours" type="number" min="0" step="0.5" value="${seg.hours ?? ""}" placeholder="如 14" />
      </label>
      <button type="button" class="btn btn-del btn-del-segment">删除段</button>
    </div>
    <div class="table-wrap">
      <table class="editable">
        <thead>
          <tr><th>温区名称</th><th>下限 ℃</th><th>上限 ℃</th><th></th></tr>
        </thead>
        <tbody class="seg-zone-rows"></tbody>
      </table>
    </div>
    <button type="button" class="btn btn-small btn-add-seg-zone">+ 添加温区</button>`;
  list.appendChild(card);
  const tbody = card.querySelector(".seg-zone-rows");
  (seg.zones?.length ? seg.zones : [{}]).forEach((z) => addZoneRow(z, tbody));
  renumberSegments();
  card.querySelector(".seg-name").focus();
  return card;
}

function renumberSegments() {
  [...$("segmentList").children].forEach((card, i) => {
    card.querySelector(".seg-no").textContent = `第 ${i + 1} 段`;
  });
}

$("btnAddSegment").addEventListener("click", () => addSegmentCard());

/* ---------------- 分段开关 ---------------- */
function toggleSegmentMode() {
  const on = $("useSegments").checked;
  $("singleZoneSection").hidden = on;
  $("segmentSection").hidden = !on;
  $("transportHoursField").classList.toggle("field-disabled", on);
  $("transportHours").disabled = on;
  if (on && !$("segmentList").children.length) addSegmentCard();
}
$("useSegments").addEventListener("change", toggleSegmentMode);

/* ---------------- 货物行 ---------------- */
function addCargoRow(c = {}) {
  addRow($("cargoRows"), [
    zoneCell(c.name, "批次名称"),
    zoneCell(c.units ?? "", "件数", "number"),
    zoneCell(c.unit_volume ?? "", "单件体积", "number"),
    zoneCell(c.t_min ?? "", "下限", "number"),
    zoneCell(c.t_max ?? "", "上限", "number"),
    `<input type="number" step="any" min="0" value="${c.max_transport_hours ?? ""}" placeholder="不限" />`,
    '<button type="button" class="btn btn-del">删除</button>',
  ]);
}

$("btnAddZone").addEventListener("click", () => addZoneRow());
$("btnAddCargo").addEventListener("click", () => addCargoRow());
document.addEventListener("click", (e) => {
  if (e.target.classList.contains("btn-del-segment")) {
    e.target.closest(".segment-card").remove();
    renumberSegments();
    return;
  }
  if (e.target.classList.contains("btn-add-seg-zone")) {
    const tbody = e.target.closest(".segment-card").querySelector(".seg-zone-rows");
    addZoneRow({}, tbody);
    return;
  }
  if (e.target.classList.contains("btn-del")) e.target.closest("tr").remove();
});

/* ---------------- 读取/校验输入 ---------------- */
function num(v, label, rowName) {
  if (v === "" || v === null || Number.isNaN(Number(v)))
    throw new Error(`${rowName ? `「${rowName}」的` : ""}${label}必须填写数字`);
  return Number(v);
}

function readRows(tbody, nFields, labels, rowPrefix = "") {
  const out = [];
  [...tbody.querySelectorAll("tr")].forEach((tr, i) => {
    const inputs = [...tr.querySelectorAll("input")];
    const rowName =
      nFields === 3 ? `${rowPrefix}温区 ${i + 1}` : (inputs[0].value || `批次 ${i + 1}`);
    const obj = {};
    inputs.forEach((inp, idx) => {
      if (idx >= labels.length) return;
      const key = labels[idx].key;
      if (labels[idx].numeric) obj[key] = num(inp.value, labels[idx].label, rowName);
      else obj[key] = inp.value.trim();
    });
    out.push(obj);
  });
  return out;
}

const ZONE_FIELDS = [
  { key: "name", label: "名称" },
  { key: "t_min", label: "下限", numeric: true },
  { key: "t_max", label: "上限", numeric: true },
];

function readZones(tbody, rowPrefix = "") {
  const zones = readRows(tbody, 3, ZONE_FIELDS, rowPrefix).map((z, i) => ({
    ...z,
    name: z.name || `温区 ${i + 1}`,
  }));
  for (const z of zones)
    if (z.t_min > z.t_max) throw new Error(`温区「${z.name}」下限不能高于上限`);
  return zones;
}

function collectSegments() {
  const cards = [...$("segmentList").children];
  if (!cards.length) throw new Error("请至少添加一个运输段");
  return cards.map((card, i) => {
    const name = card.querySelector(".seg-name").value.trim() || `第 ${i + 1} 段`;
    const hours = num(card.querySelector(".seg-hours").value, "时长", `运输段「${name}」`);
    if (hours <= 0) throw new Error(`运输段「${name}」的时长必须大于 0`);
    const zones = readZones(card.querySelector(".seg-zone-rows"), `「${name}」`);
    if (!zones.length) throw new Error(`运输段「${name}」请至少添加一个可用温区`);
    return { name, hours, zones };
  });
}

function collectInput() {
  const useSeg = $("useSegments").checked;
  const zones = useSeg ? [] : readZones($("zoneRows"));
  const segments = useSeg ? collectSegments() : [];

  const cargoes = readRows($("cargoRows"), 6, [
    { key: "name", label: "名称" },
    { key: "units", label: "件数", numeric: true },
    { key: "unit_volume", label: "单件体积", numeric: true },
    { key: "t_min", label: "温度下限", numeric: true },
    { key: "t_max", label: "温度上限", numeric: true },
    { key: "max_transport_hours", label: "最长运输时长", numeric: false },
  ]).map((c, i) => ({
    ...c,
    name: c.name || `批次 ${i + 1}`,
    max_transport_hours: c.max_transport_hours === "" ? null : Number(c.max_transport_hours),
  }));

  if (!useSeg && zones.length === 0) throw new Error("请至少添加一个允许温区");
  if (cargoes.length === 0) throw new Error("请至少添加一批货物");
  for (const c of cargoes) {
    if (c.units <= 0) throw new Error(`货物「${c.name}」件数必须大于 0`);
    if (c.unit_volume <= 0) throw new Error(`货物「${c.name}」单件体积必须大于 0`);
    if (c.t_min > c.t_max) throw new Error(`货物「${c.name}」温度下限不能高于上限`);
    if (c.max_transport_hours !== null && c.max_transport_hours < 0)
      throw new Error(`货物「${c.name}」最长运输时长不能为负`);
  }

  return {
    // 分段模式下总时长由后端按各段时长求和
    transport_hours: useSeg ? null : num($("transportHours").value, "运输时长"),
    box_capacity: num($("boxCapacity").value, "单箱容量"),
    max_boxes: num($("maxBoxes").value, "最大箱数"),
    volume_unit: $("volumeUnit").value.trim() || "体积单位",
    zones,
    segments,
    cargoes,
  };
}

/* ---------------- 渲染结果 ---------------- */
const fmt = (v) => Number(v).toLocaleString("zh-CN", { maximumFractionDigits: 2 });

const fmtSegs = (segs) =>
  segs
    .map((s) => (s.t_min === s.t_max ? `${fmt(s.t_min)}℃` : `${fmt(s.t_min)}~${fmt(s.t_max)}℃`))
    .join(" 或 ");

function renderSummary(s, unit) {
  const cls = s.all_loaded ? "ok" : "bad";
  const statusText = s.all_loaded
    ? s.segment_mode ? "✓ 全程可运输" : "✓ 全部装载"
    : "⚠ 存在冲突";
  $("summary").innerHTML = `
    <div class="stat ${cls}"><div class="k">装载状态</div>
      <div class="v"><span class="badge ${s.all_loaded ? "badge-ok" : "badge-bad"}">
        ${statusText}</span></div></div>
    <div class="stat"><div class="k">已装 / 总件数</div><div class="v">${fmt(s.loaded_units)} / ${fmt(s.total_cargo_units)}</div></div>
    <div class="stat"><div class="k">已装 / 总体积</div><div class="v">${fmt(s.loaded_volume)} / ${fmt(s.total_cargo_volume)} ${unit}</div></div>
    <div class="stat"><div class="k">使用箱数</div><div class="v">${s.boxes_used} <small class="muted">/ ${s.max_boxes}</small></div></div>
    <div class="stat"><div class="k">运输时长</div>
      <div class="v">${fmt(s.transport_hours)} h${s.segment_mode ? ' <small class="muted">分段</small>' : ""}</div></div>
    <div class="stat ${s.unloaded_units ? "bad" : "ok"}"><div class="k">未装件数</div><div class="v">${fmt(s.unloaded_units)}</div></div>
  `;
}

function renderSegmentChecks(box) {
  const rows = box.segment_checks
    .map((c) => {
      const icon = c.ok ? "✓" : "✗";
      const detail = c.ok
        ? `可设定 ${fmtSegs(c.temperature_segments)} · 设定点 ${fmt(c.recommended_setpoint)}℃ · ${c.matched_zones.map(escapeHtml).join("、")}`
        : escapeHtml(c.reason || "该段无可用温区");
      return `<tr class="${c.ok ? "seg-ok" : "seg-bad"}">
        <td class="num">${icon}</td>
        <td>第 ${c.segment_no} 段 · ${escapeHtml(c.name)}<small class="muted">（${fmt(c.hours)}h）</small></td>
        <td>${detail}</td>
      </tr>`;
    })
    .join("");
  return `
    <table class="seg-checks">
      <thead><tr><th></th><th>运输段逐段校验</th><th>可设定温度 / 失败原因</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderBox(box, unit, segmentMode) {
  const segText = fmtSegs(box.temperature_segments);
  const items = box.items
    .map(
      (it) => `<tr>
        <td>#${it.batch_no} ${escapeHtml(it.name)}</td>
        <td class="num">${fmt(it.units)} 件</td>
        <td class="num">${fmt(it.volume)} ${unit}</td>
      </tr>`
    )
    .join("");
  const pct = Math.round(box.utilization * 100);
  const transportBadge = box.transportable
    ? '<span class="badge badge-ok">✓ 全程可运输</span>'
    : '<span class="badge badge-bad">⚠ 分段不兼容</span>';
  const card = document.createElement("div");
  card.className = "box-card";
  card.innerHTML = `
    <div class="box-head">
      <span class="box-title">📦 第 ${box.box_no} 箱 ${segmentMode ? transportBadge : ""}</span>
      <span><span class="temp-chip">${fmt(box.temperature_range.t_min)} ~ ${fmt(box.temperature_range.t_max)} ℃</span>
      <span class="temp-segments">可设定: ${segText}</span></span>
    </div>
    <div class="meta-line">
      推荐设定温度 <strong>${fmt(box.recommended_setpoint)}℃</strong> ·
      匹配温区: ${box.matched_zones.map(escapeHtml).join("、")} ·
      容量 ${fmt(box.used_volume)} / ${fmt(box.capacity)} ${unit}（${pct}%）
    </div>
    <div class="cap-bar"><i style="width:${pct}%"></i></div>
    ${segmentMode ? renderSegmentChecks(box) : ""}
    <table class="items">
      <thead><tr><th>装载批次</th><th class="num">件数</th><th class="num">占用体积</th></tr></thead>
      <tbody>${items}</tbody>
    </table>`;
  $("boxes").appendChild(card);
}

function renderUnloaded(unloaded, unit) {
  const wrap = $("unloaded");
  wrap.innerHTML = "";
  if (!unloaded.length) {
    $("unloadedTitle").hidden = true;
    return;
  }
  $("unloadedTitle").hidden = false;
  unloaded.forEach((u) => {
    const segBadge = u.failed_segment_name
      ? `<span class="seg-badge">首次不兼容:第 ${u.failed_segment_no} 段 · ${escapeHtml(u.failed_segment_name)}</span>`
      : "";
    const div = document.createElement("div");
    div.className = "unloaded-item";
    div.innerHTML = `
      <div class="u-title">⛔ #${u.batch_no} ${escapeHtml(u.name)} — 未能装载 ${fmt(u.units)} 件（${fmt(u.volume)} ${unit}）${segBadge}</div>
      <div class="u-reason">原因：${escapeHtml(u.reason)}</div>`;
    wrap.appendChild(div);
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

/* ---------------- 提交 ---------------- */
async function runPlan() {
  const btn = $("btnPlan");
  $("errorBox").hidden = true;
  let payload;
  try {
    payload = collectInput();
  } catch (e) {
    showError(e.message);
    return;
  }
  btn.disabled = true;
  btn.textContent = "规划中…";
  try {
    const resp = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || `规划失败（HTTP ${resp.status}）`);
    renderResult(data);
  } catch (e) {
    showError(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "▶ 生成分箱方案";
  }
}

function renderResult(data) {
  $("resultPlaceholder").hidden = true;
  $("resultView").hidden = false;
  renderSummary(data.summary, data.volume_unit);
  $("boxCount").textContent = `（共 ${data.boxes.length} 箱）`;
  $("boxes").innerHTML = "";
  data.boxes.forEach((b) => renderBox(b, data.volume_unit, data.summary.segment_mode));
  renderUnloaded(data.unloaded, data.volume_unit);
}

function showError(msg) {
  $("resultPlaceholder").hidden = true;
  $("resultView").hidden = true;
  $("errorBox").hidden = false;
  $("errorBox").textContent = "⚠ " + msg;
}

$("btnPlan").addEventListener("click", runPlan);

$("btnSample").addEventListener("click", () => {
  $("transportHours").value = SAMPLE.transport_hours;
  $("boxCapacity").value = SAMPLE.box_capacity;
  $("maxBoxes").value = SAMPLE.max_boxes;
  $("volumeUnit").value = SAMPLE.volume_unit;
  $("useSegments").checked = !!SAMPLE.use_segments;
  toggleSegmentMode();
  $("zoneRows").innerHTML = "";
  $("cargoRows").innerHTML = "";
  $("segmentList").innerHTML = "";
  SAMPLE.zones.forEach((z) => addZoneRow(z));
  SAMPLE.segments.forEach((s) => addSegmentCard(s));
  SAMPLE.cargoes.forEach(addCargoRow);
  showError("");
  $("errorBox").hidden = true;
  $("resultView").hidden = true;
  $("resultPlaceholder").hidden = false;
});

/* ---------------- 初始空行 ---------------- */
addZoneRow({ name: "冷藏区", t_min: 0, t_max: 8 });
addCargoRow({ name: "", units: "", unit_volume: "", t_min: "", t_max: "" });

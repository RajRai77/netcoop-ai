// NetCoop AI browser UI. Renders only what the API returns; never invents state.
// All dynamic text goes through text nodes (no innerHTML with data) to avoid injection.
"use strict";

const S = { incident: null, tab: "report", poll: null, profiles: [], meta: null, report: null };

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c instanceof Node ? c : String(c));
  return e;
}
const $ = (id) => document.getElementById(id);
const clear = (n) => { while (n.firstChild) n.removeChild(n.firstChild); return n; };
const pill = (text, cls) => el("span", { class: "pill " + (cls || "") }, text);
const statusPill = (s) => pill(s || "no report", "st-" + (s || ""));

function token() { return sessionStorage.getItem("netcoop_token"); }
async function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  if (token()) headers["Authorization"] = "Bearer " + token();
  const r = await fetch(path, Object.assign({}, opts, { headers }));
  if (r.status === 401) {
    const t = prompt("This deployment requires an API token:");
    if (t) { sessionStorage.setItem("netcoop_token", t); return api(path, opts); }
  }
  const text = await r.text();
  let body; try { body = JSON.parse(text); } catch { body = text; }
  if (!r.ok) {
    const msg = body && body.error ? `${body.error.code}: ${(body.error.issues || []).map(i => i.message).join("; ") || body.error.message}`
      : (body && body.detail ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)) : text);
    throw new Error(`HTTP ${r.status} — ${msg}`);
  }
  return body;
}
function showModal(obj) { $("modal-body").textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2); $("modal").classList.remove("hidden"); }
$("modal-close").onclick = () => $("modal").classList.add("hidden");
function errBox(e) { return el("div", { class: "err" }, String(e.message || e)); }
function table(headers, rows) {
  return el("table", { class: "grid" }, el("thead", {}, el("tr", {}, headers.map(h => el("th", {}, h)))), el("tbody", {}, rows));
}

// ---------------------------------------------------------------- platform & history
async function loadPlatform() {
  const p = clear($("platform"));
  try {
    const [h, meta, ag] = await Promise.all([fetch("/health/ready").then(r => r.json()), api("/api/meta"), api("/api/agents")]);
    S.meta = meta;
    p.append(pill("DB " + (h.status === "ready" ? "ready" : "NOT ready"), h.status === "ready" ? "st-diagnosed" : "st-operational_error"));
    p.append(pill("agent transport: " + meta.agent_transport, meta.agent_transport === "a2a" ? "st-diagnosed" : "st-ambiguous"));
    for (const a of ag.agents) p.append(pill(`${a.agent_id}: ${a.status}`, a.status === "available" ? "st-diagnosed" : "st-operational_error"));
    if (!ag.agents.length) p.append(pill("no specialist agents configured", "st-operational_error"));
    p.append(pill(`rules ${meta.detector_rules} · ${meta.fault_library}`));
  } catch (e) { p.append(pill("platform check failed: " + e.message, "st-operational_error")); }
}

async function loadHistory() {
  const ul = clear($("incident-list"));
  try {
    const { incidents } = await api("/api/incidents");
    if (!incidents.length) ul.append(el("li", { class: "small" }, "No incidents yet."));
    for (const i of incidents) {
      const wf = i.workflow ? i.workflow.state : "NEW";
      const lr = i.latest_report;
      ul.append(el("li", { class: S.incident === i.incident_id ? "active" : "", onclick: () => openIncident(i.incident_id) },
        el("div", { class: "t" }, i.title || i.incident_id),
        el("div", { class: "s" }, lr ? statusPill(lr.status) : pill(wf, "st-running"), pill(i.data_mode, "mode"),
          el("span", { class: "mono" }, i.incident_id.slice(0, 12)))));
    }
  } catch (e) { ul.append(el("li", {}, errBox(e))); }
}

// ---------------------------------------------------------------- new incident
function setTabs(container, tab, onPick) {
  for (const b of container.querySelectorAll("button")) {
    b.classList.toggle("active", b.dataset.tab === tab);
    b.onclick = () => onPick(b.dataset.tab);
  }
}
async function showNew() {
  S.incident = null; stopPoll();
  $("view-incident").classList.add("hidden"); $("view-empty").classList.add("hidden"); $("view-new").classList.remove("hidden");
  const pick = (t) => { setTabs($("new-tabs"), t, pick); $("tab-scenario").classList.toggle("hidden", t !== "scenario"); $("tab-upload").classList.toggle("hidden", t !== "upload"); };
  pick("scenario");
  const tb = clear($("scenario-rows"));
  try {
    const { scenarios } = await api("/api/scenarios");
    if (!scenarios.length) tb.append(el("tr", {}, el("td", { colspan: 4 }, "No packaged scenarios configured.")));
    for (const s of scenarios) {
      tb.append(el("tr", {},
        el("td", {}, el("b", {}, s.scenario_id), el("div", { class: "small" }, s.title), el("div", {}, pill(s.data_mode, "mode"), s.telemetry_profile ? pill("CSV profile " + s.telemetry_profile) : null)),
        el("td", {}, (s.tags || []).map(t => pill(t))),
        el("td", {}, s.has_archive ? "yes (recorded, on request)" : "none"),
        el("td", {}, el("button", { class: "primary", onclick: (ev) => createFromScenario(s.scenario_id, ev.target) }, "Create & diagnose"))));
    }
  } catch (e) { tb.append(el("tr", {}, el("td", { colspan: 4 }, errBox(e)))); }
  try {
    const { profiles } = await api("/api/profiles");
    S.profiles = profiles;
    const f = clear($("up-format"));
    f.append(el("option", { value: "ndep" }, "NDEP TelemetryBatch JSON"));
    for (const p of profiles) f.append(el("option", { value: p.profile_id }, `${p.format.toUpperCase()} via profile ${p.profile_id}@${p.version}`));
  } catch (e) { /* profiles optional */ }
}

async function createFromScenario(id, btn) {
  btn.disabled = true; btn.textContent = "loading…";
  try {
    const r = await api("/api/incidents", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario_id: id }) });
    const iid = r.incident.incident_id;
    await api(`/api/incidents/${iid}/diagnose`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ verification: $("sc-verify").checked }) });
    await loadHistory(); openIncident(iid);
  } catch (e) { btn.parentElement.append(errBox(e)); btn.disabled = false; btn.textContent = "Create & diagnose"; }
}

async function readFile(input) { const f = input.files[0]; return f ? await f.text() : null; }
$("btn-upload").onclick = async () => {
  const out = clear($("upload-result"));
  try {
    const tel = await readFile($("up-tel"));
    if (!tel) throw new Error("Choose a telemetry file.");
    const topoText = await readFile($("up-topo"));
    const body = { data_mode: $("up-mode").value, title: $("up-title").value || null };
    if ($("up-ref").value) body.reference_time = $("up-ref").value;
    if (topoText) body.topology = JSON.parse(topoText);
    const inc = (await api("/api/incidents", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).incident;
    const fmt = $("up-format").value;
    const q = fmt === "ndep" ? "" : `?profile=${encodeURIComponent(fmt)}`;
    let report;
    try {
      report = await api(`/api/incidents/${inc.incident_id}/telemetry${q}`, { method: "POST", headers: { "Content-Type": fmt === "ndep" ? "application/json" : "text/csv" }, body: tel });
    } catch (e) { out.append(errBox(e)); }
    const arch = await readFile($("up-archive"));
    if (arch) {
      try { await api(`/api/incidents/${inc.incident_id}/archive`, { method: "POST", headers: { "Content-Type": "application/json" }, body: arch }); }
      catch (e) { out.append(errBox("archive: " + e.message)); }
    }
    if (report) out.append(ingestionView(report));
    out.append(el("button", { class: "primary", onclick: () => openIncident(inc.incident_id) }, "Open incident " + inc.incident_id));
    loadHistory();
  } catch (e) { out.append(errBox(e)); }
};

function ingestionView(rep) {
  const c = rep.counts;
  return el("div", {},
    el("h4", {}, "Validation result"),
    el("div", { class: "summary" }, Object.entries(c).map(([k, v]) => el("div", { class: "box" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v)))),
    rep.issues.length ? table(["severity", "code", "record", "message"], rep.issues.slice(0, 200).map(i =>
      el("tr", {}, el("td", {}, pill(i.severity, i.severity === "reject" ? "st-operational_error" : i.severity === "quarantine" ? "st-ambiguous" : "")),
        el("td", { class: "mono" }, i.code), el("td", { class: "mono" }, i.record_id ?? i.record_index ?? "batch"), el("td", {}, i.message)))) : el("p", {}, "No issues."));
}

// ---------------------------------------------------------------- incident view
function stopPoll() { if (S.poll) { clearInterval(S.poll); S.poll = null; } }

async function openIncident(iid) {
  stopPoll(); S.incident = iid; S.tab = "report";
  $("view-new").classList.add("hidden"); $("view-empty").classList.add("hidden"); $("view-incident").classList.remove("hidden");
  for (const li of document.querySelectorAll("#incident-list li")) li.classList.remove("active");
  await refreshIncident(true);
  S.poll = setInterval(() => refreshIncident(false), 1500);
  loadHistory();
}

const FLOW = ["NEW", "VALIDATING", "DISCOVERING", "INVESTIGATING", "CORRELATING", "VERIFYING"];
async function refreshIncident(force) {
  const iid = S.incident; if (!iid) return;
  let info;
  try { info = await api(`/api/incidents/${iid}`); } catch (e) { clear($("pane")).append(errBox(e)); stopPoll(); return; }
  const inc = info.incident;
  $("inc-title").textContent = inc.title || inc.incident_id;
  const m = clear($("inc-meta"));
  m.append(pill("data mode: " + inc.data_mode, "mode"), el("span", { class: "mono" }, inc.incident_id),
    inc.scenario_id ? pill("scenario " + inc.scenario_id) : null, inc.topology_snapshot_id ? pill("topology " + inc.topology_snapshot_id) : pill("no topology", "st-ambiguous"),
    inc.archive_ref ? pill("archive " + inc.archive_ref) : pill("no archive"),
    inc.reference_time ? pill("captured at " + inc.reference_time) : null,
    el("span", {}, `${info.evidence_counts.observations} observations · ${info.evidence_counts.raw_records} raw records · ${info.evidence_counts.issues} issues · ${info.evidence_counts.findings} findings`));
  $("btn-diagnose").disabled = info.running;
  $("btn-diagnose").textContent = info.running ? "Running…" : (info.reports.length ? "Re-run diagnosis (new revision)" : "Run diagnosis");
  // progress: real workflow events of the latest run
  const tl = await api(`/api/incidents/${iid}/timeline`).catch(() => null);
  const prog = clear($("progress"));
  if (tl && tl.events.length) {
    const runId = tl.events[tl.events.length - 1].run_id;
    const evs = tl.events.filter(e => e.run_id === runId);
    const seen = new Set(evs.map(e => e.state));
    const last = evs[evs.length - 1].state;
    prog.append(el("div", { class: "steps" }, el("b", {}, "Run " + runId + ": "),
      FLOW.map(s => el("span", { class: "step" + (seen.has(s) ? " done" : "") }, s)), el("span", {}, "→"),
      el("span", { class: "step final" }, info.running ? "in progress (" + last + ")" : last)));
  } else prog.append(el("span", { class: "small" }, "No diagnosis run yet."));
  if (force || info.running || S.lastRunning) await renderTab(info, tl);
  S.lastRunning = info.running;
  if (!info.running && !force && S.poll && S.stablePolls++ > 3) stopPoll();
  if (info.running) S.stablePolls = 0;
}

$("btn-diagnose").onclick = async () => {
  try {
    $("btn-diagnose").disabled = true;
    await api(`/api/incidents/${S.incident}/diagnose`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ verification: $("inc-verify").checked }) });
    S.stablePolls = 0; stopPoll(); S.poll = setInterval(() => refreshIncident(false), 1500); refreshIncident(false);
  } catch (e) { clear($("pane")).append(errBox(e)); $("btn-diagnose").disabled = false; }
};

async function renderTab(info, tl) {
  setTabs($("inc-tabs"), S.tab, (t) => { S.tab = t; renderTab(info, tl); });
  const pane = clear($("pane"));
  const iid = S.incident;
  try {
    if (S.tab === "report") return renderReport(pane, info);
    if (S.tab === "hyp") return renderHypotheses(pane, info);
    if (S.tab === "verify") return renderVerification(pane, tl);
    if (S.tab === "agents") return renderAgents(pane, tl);
    if (S.tab === "timeline") return renderTimeline(pane, tl);
    if (S.tab === "evidence") return renderEvidence(pane, iid);
    if (S.tab === "findings") return renderFindings(pane, iid);
    if (S.tab === "topology") return renderTopology(pane, iid, info);
  } catch (e) { pane.append(errBox(e)); }
}

async function latestReport(info, rev) {
  if (!info.reports.length) return null;
  return api(`/api/incidents/${S.incident}/report` + (rev ? `?revision=${rev}` : ""));
}

async function renderReport(pane, info) {
  const r = await latestReport(info, S.revision && info.reports.some(x => x.revision === S.revision) ? S.revision : null);
  if (!r) { pane.append(el("p", {}, "No report yet. Run a diagnosis.")); return; }
  S.report = r;
  const revSel = el("select", { onchange: (e) => { S.revision = Number(e.target.value); renderReport(clear(pane), info); } },
    info.reports.map(x => el("option", { value: x.revision, selected: x.revision === r.revision }, `revision ${x.revision} · ${x.status} · ${x.created_at}`)));
  pane.append(el("div", { class: "meta" }, "Report ", revSel,
    el("a", { href: `/api/incidents/${S.incident}/report?revision=${r.revision}`, target: "_blank", download: `${S.incident}-r${r.revision}.json` }, "download JSON"),
    el("a", { href: `/api/incidents/${S.incident}/report.txt?revision=${r.revision}`, target: "_blank" }, "text"),
    el("button", { onclick: () => showModal(r) }, "view raw JSON")));
  pane.append(el("div", { class: "summary" },
    box("Status", statusPill(r.status)), box("Support category", r.confidence_category.replace(/_/g, " ")),
    box("Probable root cause", r.suspected_root_cause || "not determined"),
    box("Affected", (r.affected_devices || []).join(", ") || "—"),
    box("Transport", r.transport), box("Evidence sources", (r.evidence_sources || []).join(", ") || "—")));
  pane.append(el("p", {}, r.explanation));
  pane.append(el("p", { class: "small" }, "Support categories are documented decision rules, not probabilities."));
  section(pane, "Why", r.decision_basis);
  pane.append(el("h4", {}, `Supporting evidence (${r.supporting_evidence.length})`));
  pane.append(table(["metric", "value", "unit", "interpretation", "observation"], r.supporting_evidence.map(e =>
    el("tr", { class: "clickable", onclick: () => showObservation(e.observation_id) }, el("td", {}, e.metric), el("td", { class: "mono" }, String(e.value)),
      el("td", {}, e.unit), el("td", {}, e.interpretation), el("td", { class: "mono" }, e.observation_id)))));
  section(pane, "Alternatives considered", r.alternative_causes);
  section(pane, "Recommended actions (operator review; nothing is executed)", r.recommended_actions);
  section(pane, "Limitations", r.limitations);
  if ((r.unexplained_symptoms || []).length) section(pane, "Unexplained symptom findings", r.unexplained_symptoms);
  pane.append(el("p", { class: "small mono" }, `snapshot ${r.evidence_snapshot_id} · topology ${r.topology_snapshot_id} · engine ${r.engine_version} · ${JSON.stringify(r.knowledge_versions)}`));
}
function box(k, v) { return el("div", { class: "box" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v)); }
function section(pane, title, items) {
  if (!items || !items.length) return;
  pane.append(el("h4", {}, title), el("ul", { class: "plain" }, items.map(x => el("li", {}, x))));
}
async function showObservation(oid) {
  const ev = await api(`/api/incidents/${S.incident}/evidence?limit=2000`);
  const o = ev.observations.find(x => x.observation_id === oid);
  if (!o) return showModal("observation not found");
  const raw = await api(`/api/raw-records/${o.raw_record_ref}`).catch(() => null);
  showModal({ observation: o, raw_record: raw });
}

async function renderHypotheses(pane, info) {
  const r = await latestReport(info);
  if (!r) { pane.append(el("p", {}, "No report yet.")); return; }
  pane.append(el("p", { class: "hint" }, "Every candidate the engine generated (top 40), ranked lexicographically: confirmed signature > more symptoms explained > more independent lineage groups > fewer missing discriminators > fewer temporal issues > more specific location. Click a row for details."));
  pane.append(table(["#", "fault", "location", "status", "explains", "lineage groups", "missing", "contradictions"],
    (r.hypotheses || []).map(h => el("tr", { class: "clickable", onclick: () => showModal(h) },
      el("td", {}, h.rank), el("td", {}, h.fault_type), el("td", { class: "mono" }, h.location),
      el("td", {}, pill(h.status, h.status === "confirmed" ? "st-diagnosed" : h.status === "plausible" ? "st-ambiguous" : "st-operational_error")),
      el("td", {}, h.explained_findings.length), el("td", {}, h.independent_lineage_groups),
      el("td", { class: "small" }, h.missing_discriminators.map(m => m.claim).join(", ")),
      el("td", { class: "small" }, (h.contradictions || [])[0] || "")))));
}

function renderVerification(pane, tl) {
  const chs = (tl && tl.challenges) || [];
  pane.append(el("p", { class: "hint" }, "Targeted checks chosen by the planner to separate competing hypotheses. Agents answer only from authorized recorded sources; 'unavailable' means nothing was measured and nothing was invented."));
  if (!chs.length) { pane.append(el("p", {}, "No verification challenges were issued.")); return; }
  pane.append(table(["challenge", "to agent", "requested", "hypotheses", "outcome", "new observations", "note"], chs.map(c => {
    const o = c.outcomes[c.outcomes.length - 1];
    const d = o ? o.detail : {};
    return el("tr", { class: "clickable", onclick: () => showModal(c) },
      el("td", { class: "mono" }, c.challenge.challenge_id), el("td", {}, c.challenge.target_agent_id),
      el("td", {}, `${c.challenge.requested_observation.metric} @ ${JSON.stringify(c.challenge.requested_observation.subject)}`),
      el("td", { class: "small" }, c.challenge.hypothesis_ids.join(", ")),
      el("td", {}, o ? pill(o.outcome, o.outcome === "obtained" ? "st-diagnosed" : "st-ambiguous") : pill("pending", "st-running")),
      el("td", {}, (d.new_observation_ids || []).length), el("td", { class: "small" }, d.note || ""));
  })));
}

function renderAgents(pane, tl) {
  const at = (tl && tl.attempts) || [];
  pane.append(el("p", { class: "hint" }, "Every message exchanged with a specialist: logical task id (idempotency key), attempt, transport, real A2A task/message ids, and the outcome after validation. Click to see the exact NDEP artifact returned."));
  if (!at.length) { pane.append(el("p", {}, "No agent tasks yet.")); return; }
  pane.append(table(["started", "agent", "task", "attempt", "transport", "A2A task id", "outcome", "findings stored"], at.map(a =>
    el("tr", { class: "clickable", onclick: async () => showModal(await api(`/api/incidents/${S.incident}/attempts/${a.attempt_id}`)) },
      el("td", { class: "mono" }, a.started_at.slice(11, 23)), el("td", {}, a.agent_id), el("td", {}, a.task_type),
      el("td", {}, a.attempt_no), el("td", {}, pill(a.transport, a.transport === "a2a" ? "st-diagnosed" : "st-ambiguous")),
      el("td", { class: "mono" }, a.detail.a2a_task_id || "—"),
      el("td", {}, pill(a.outcome, a.outcome === "completed" ? "st-diagnosed" : "st-operational_error")),
      el("td", {}, (a.detail.findings_stored || []).length + (a.detail.findings_unchanged ? ` (+${a.detail.findings_unchanged.length} unchanged)` : ""))))));
}

function renderTimeline(pane, tl) {
  const evs = (tl && tl.events) || [];
  if (!evs.length) { pane.append(el("p", {}, "No events.")); return; }
  pane.append(table(["#", "time", "run", "state", "actor", "detail"], evs.map(e =>
    el("tr", { class: "clickable", onclick: () => showModal(e) }, el("td", {}, e.seq), el("td", { class: "mono" }, e.at.slice(11, 23)),
      el("td", { class: "mono" }, e.run_id.slice(0, 12)), el("td", {}, pill(e.state, "st-" + e.state.toLowerCase())),
      el("td", {}, e.actor), el("td", { class: "small mono" }, JSON.stringify(e.detail).slice(0, 160))))));
}

async function renderEvidence(pane, iid) {
  const ev = await api(`/api/incidents/${iid}/evidence?limit=2000`);
  const metrics = [...new Set(ev.observations.map(o => o.measurement.metric))].sort();
  const sel = el("select", {}, el("option", { value: "" }, "all metrics"), metrics.map(m => el("option", { value: m }, m)));
  const holder = el("div");
  const draw = () => {
    clear(holder);
    const rows = ev.observations.filter(o => !sel.value || o.measurement.metric === sel.value).slice(0, 600);
    holder.append(table(["observed (UTC)", "subject", "metric", "value", "unit", "source", "quality"], rows.map(o =>
      el("tr", { class: "clickable", onclick: () => showObservation(o.observation_id) },
        el("td", { class: "mono" }, o.observed_at.slice(0, 19)), el("td", { class: "mono" }, Object.values(o.subject).join(":")),
        el("td", {}, o.measurement.metric), el("td", { class: "mono" }, String(o.measurement.value)), el("td", {}, o.measurement.unit),
        el("td", {}, o.source.source_id), el("td", {}, pill(o.quality.validation, o.quality.validation === "passed" ? "" : "st-ambiguous"),
          o.quality.freshness !== "current" ? pill(o.quality.freshness, "st-ambiguous") : null, el("span", { class: "small" }, " " + o.quality.flags.join(", ")))))));
  };
  sel.onchange = draw;
  pane.append(el("div", { class: "meta" }, `${ev.observations.length} observation(s) (showing up to 600) · ${ev.derived_rates.length} derived counter rate(s) · ${ev.issues.length} validation issue(s) · filter `, sel));
  pane.append(holder); draw();
  if (ev.issues.length) {
    pane.append(el("h4", {}, "Validation issues"));
    pane.append(table(["severity", "code", "record", "message"], ev.issues.slice(0, 300).map(i =>
      el("tr", {}, el("td", {}, i.severity), el("td", { class: "mono" }, i.code), el("td", { class: "mono" }, i.record_index ?? "—"), el("td", {}, i.message)))));
  }
  if (ev.derived_rates.length) {
    pane.append(el("h4", {}, "Derived counter rates (persisted, with input lineage)"));
    pane.append(table(["window end", "subject", "rate metric", "value", "inputs"], ev.derived_rates.slice(0, 200).map(r =>
      el("tr", {}, el("td", { class: "mono" }, r.window_end.slice(0, 19)), el("td", { class: "mono" }, r.subject_key), el("td", {}, r.rate_metric),
        el("td", { class: "mono" }, r.value.toFixed(3) + " " + r.unit), el("td", { class: "mono small" }, r.input_observation_ids.join(", "))))));
  }
}

async function renderFindings(pane, iid) {
  const { findings } = await api(`/api/incidents/${iid}/findings?all_revisions=true`);
  if (!findings.length) { pane.append(el("p", {}, "No findings yet.")); return; }
  const byAgent = {};
  for (const f of findings) (byAgent[f.agent_id] = byAgent[f.agent_id] || []).push(f);
  for (const [agent, fs] of Object.entries(byAgent)) {
    const present = fs.filter(f => f.polarity === "present").length;
    pane.append(el("h4", {}, `${agent} — ${fs.length} finding(s), ${present} present`));
    pane.append(table(["claim", "polarity", "subject", "observations", "supersedes", "caveats"], fs.map(f =>
      el("tr", { class: "clickable", onclick: () => showModal(f) }, el("td", {}, f.claim),
        el("td", {}, pill(f.polarity, f.polarity === "present" ? "st-ambiguous" : f.polarity === "absent" ? "st-healthy" : "")),
        el("td", { class: "mono" }, Object.values(f.subject).join(":")), el("td", {}, f.observation_refs.length),
        el("td", { class: "mono small" }, f.supersedes_finding_id || ""), el("td", { class: "small" }, f.caveats.join("; "))))));
  }
}

async function renderTopology(pane, iid, info) {
  const { topology } = await api(`/api/incidents/${iid}/topology`);
  if (!topology) { pane.append(el("p", {}, "No topology snapshot for this incident — localization is limited to measured components (stated in the report limitations).")); return; }
  const r = info.reports.length ? await latestReport(info) : null;
  const cause = new Set(); const affected = new Set(); const symptomatic = new Set();
  if (r) {
    for (const rc of r.root_causes || []) cause.add(rc.location.split(":")[0]);
    for (const a of r.affected_devices || []) affected.add(a);
    for (const h of r.hypotheses || []) if (h.status !== "contradicted") symptomatic.add(h.location.split(":")[0]);
  }
  // layered layout: BFS depth from core nodes over physical/logical links
  const nodes = topology.nodes; const phys = topology.links.filter(l => l.type !== "dependency");
  const adj = {}; for (const n of nodes) adj[n.id] = [];
  for (const l of phys) { adj[l.from]?.push(l.to); adj[l.to]?.push(l.from); }
  const depth = {}; const q = nodes.filter(n => n.role === "core").map(n => n.id);
  for (const c of q) depth[c] = 0;
  while (q.length) { const c = q.shift(); for (const n of adj[c] || []) if (depth[n] === undefined) { depth[n] = depth[c] + 1; q.push(n); } }
  for (const n of nodes) if (depth[n.id] === undefined) depth[n.id] = n.type === "service" ? 1 : 0;
  const levels = {}; for (const n of nodes) (levels[depth[n.id]] = levels[depth[n.id]] || []).push(n);
  const W = Math.max(900, Math.max(...Object.values(levels).map(l => l.length)) * 90), H = (Object.keys(levels).length) * 110 + 40;
  const pos = {};
  for (const [d, ns] of Object.entries(levels)) ns.forEach((n, i) => { pos[n.id] = [((i + 0.5) * W) / ns.length, 40 + Number(d) * 110]; });
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg"); svg.setAttribute("width", W); svg.setAttribute("height", H);
  const mk = (t, a) => { const e = document.createElementNS(NS, t); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); return e; };
  for (const l of topology.links) {
    if (!pos[l.from] || !pos[l.to]) continue;
    svg.append(mk("line", { x1: pos[l.from][0], y1: pos[l.from][1], x2: pos[l.to][0], y2: pos[l.to][1], stroke: l.type === "dependency" ? "#c084fc" : "#94a3b8", "stroke-dasharray": l.type === "dependency" ? "4 3" : "", "stroke-width": 1.5 }));
  }
  for (const n of nodes) {
    const [x, y] = pos[n.id];
    const color = cause.has(n.id) ? "#dc2626" : affected.has(n.id) ? "#f59e0b" : symptomatic.has(n.id) ? "#fde68a" : n.type === "service" ? "#e9d5ff" : "#e2e8f0";
    const g = mk("g", {});
    g.append(mk("circle", { cx: x, cy: y, r: n.type === "host" ? 9 : 15, fill: color, stroke: "#334155", "stroke-width": 1 }));
    const t = mk("text", { x, y: y + 28, "text-anchor": "middle", "font-size": 10, fill: "#1e293b" }); t.textContent = n.id;
    const title = mk("title", {}); title.textContent = `${n.id} (${n.type}${n.role ? ", " + n.role : ""}${n.service_kind ? ", " + n.service_kind : ""})`;
    g.append(t, title); svg.append(g);
  }
  pane.append(el("div", { class: "legend" }, el("span", { style: "--c:#dc2626" }, "root-cause location"), el("span", { style: "--c:#f59e0b" }, "affected"),
    el("span", { style: "--c:#fde68a" }, "location of a surviving hypothesis"), el("span", { style: "--c:#e9d5ff" }, "service"), el("span", { style: "--c:#c084fc" }, "dependency link (dashed)")));
  pane.append(el("div", { class: "topo-wrap" }, svg));
  pane.append(el("p", { class: "small" }, `Snapshot ${topology.topology_snapshot_id} (${topology.kind}). ${(topology.limitations || []).join(" ")}`));
}

// ---------------------------------------------------------------- boot
$("btn-new").onclick = showNew;
loadPlatform(); loadHistory();
setInterval(loadHistory, 10000);

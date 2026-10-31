// Frontend smoke test: loads the REAL index.html + app.js into jsdom, wires fetch to a
// running NetCoop server, drives the UI (create scenario incident, run diagnosis), and
// asserts that the DOM shows the backend's actual report. Not a pixel/visual test.
//
//   BASE_URL=http://127.0.0.1:8000 node ui_smoke.mjs
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

const BASE = process.env.BASE_URL || "http://127.0.0.1:8000";
const SCENARIO = process.env.SCENARIO || "S04-device-down";
const root = new URL("../../src/netcoop/web/", import.meta.url);
const html = readFileSync(new URL("index.html", root), "utf8").replace(/<script src="\/static\/app.js"><\/script>/, "");
const js = readFileSync(new URL("app.js", root), "utf8");

const dom = new JSDOM(html, { url: BASE + "/", runScripts: "outside-only", pretendToBeVisual: true });
const w = dom.window;
w.fetch = (p, o) => fetch(new URL(p, BASE), o);
w.prompt = () => null;
w.alert = (m) => console.log("alert:", m);
const errors = [];
w.addEventListener("error", (e) => errors.push(String(e.error || e.message)));
w.eval(js);

const doc = w.document;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, what, ms = 90000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { const v = fn(); if (v) return v; await sleep(300); }
  throw new Error("timeout waiting for " + what);
}
const text = (id) => doc.getElementById(id).textContent;
let failures = 0;
const check = (name, ok, detail = "") => { console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " (" + detail + ")" : ""}`); if (!ok) failures++; };

try {
  await until(() => /agent transport/.test(text("platform")), "platform status");
  check("platform shows A2A transport and agents", /agent transport: a2a/.test(text("platform")) && /performance-agent: available/.test(text("platform")), text("platform").slice(0, 160));

  doc.getElementById("btn-new").click();
  const row = await until(() => [...doc.querySelectorAll("#scenario-rows tr")].find((tr) => tr.textContent.includes(SCENARIO)), "scenario list");
  check("scenario list rendered from API", !!row);
  row.querySelector("button").click();

  await until(() => !doc.getElementById("view-incident").classList.contains("hidden"), "incident view");
  check("incident view opened", true, text("inc-title"));
  await until(() => /Probable root cause/.test(text("pane")) && /DIAGNOSED|AMBIGUOUS|HEALTHY|UNKNOWN_FAULT|INSUFFICIENT/.test(text("progress")), "report in pane", 120000);
  const pane = text("pane");
  const iid = doc.querySelector("#inc-meta .mono").textContent;
  const report = await (await fetch(`${BASE}/api/incidents/${iid}/report`)).json();
  check("UI shows the backend's status", pane.includes(report.status), report.status);
  check("UI shows the backend's root cause", pane.includes(report.suspected_root_cause || "not determined"), report.suspected_root_cause);
  check("UI lists supporting evidence ids", report.supporting_evidence.slice(0, 3).every((e) => pane.includes(e.observation_id)));
  check("data mode label visible", /data mode: synthetic/.test(text("inc-meta")));

  for (const [tab, needle] of [["agents", "a2a"], ["timeline", "CORRELATING"], ["hyp", report.hypotheses[0].fault_type], ["evidence", "observation(s)"], ["topology", "root-cause location"]]) {
    doc.querySelector(`#inc-tabs button[data-tab="${tab}"]`).click();
    await until(() => text("pane").includes(needle), `tab ${tab}`, 30000).then(() => check(`tab '${tab}' renders backend data`, true), (e) => check(`tab '${tab}' renders backend data`, false, e.message));
  }
  check("no uncaught script errors", errors.length === 0, errors.join(" | "));
} catch (e) {
  check("ui flow", false, e.message);
} finally {
  w.close();
}
console.log(failures ? `${failures} check(s) failed` : "all UI checks passed");
process.exit(failures ? 1 : 0);

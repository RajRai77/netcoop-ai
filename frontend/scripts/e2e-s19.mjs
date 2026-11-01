// End-to-end browser test of the golden scenario against a REAL running backend (no preview data).
//   node scripts/e2e-s19.mjs [uiBaseUrl] [outDir]
// Drives the UI like a user: picks S19 in the sidebar launcher, runs the diagnosis, follows the live
// SSE stream to a terminal state, then checks the timeline, reasoning and report pages and exports the
// report JSON. Every assertion is compared with the backend's own API response for the same incident.
import puppeteer from 'puppeteer-core';
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const [base = 'http://127.0.0.1:5173', out = 'docs/e2e-s19'] = process.argv.slice(2);
const SCENARIO = 'S19-ap-down-status-in-archive';
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium'].find((p) => existsSync(p));
if (!chrome) throw new Error('No Chrome/Edge found');
const outDir = resolve(out);
const dlDir = resolve(out, 'download');
mkdirSync(dlDir, { recursive: true });

const steps = [];
const check = (name, ok, detail = '') => {
  steps.push({ name, ok: !!ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const api = async (path) => {
  const r = await fetch(base + path);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
};

const browser = await puppeteer.launch({ executablePath: chrome, headless: true, args: ['--force-color-profile=srgb'] });
const errors = [];
const streamRequests = [];
let incidentId = null;
try {
  const page = await browser.newPage();
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => m.type() === 'error' && errors.push(`console: ${m.text()}`));
  page.on('request', (r) => r.url().includes('/stream') && streamRequests.push(r.url()));
  await page.setViewport({ width: 1536, height: 960 });
  const cdp = await page.createCDPSession();
  await cdp.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: dlDir });
  await page.evaluateOnNewDocument(() => {
    if (!sessionStorage.getItem('e2e-init')) {
      sessionStorage.setItem('e2e-init', '1');
      localStorage.setItem('netcoop-ui-v2', JSON.stringify({ state: { apiBase: '', apiToken: '', preview: false, reducedMotion: true,
        activeIncidentId: null, selectedScenarioId: null }, version: 0 }));
    }
  });

  // 1. Backend reachable and connected (not preview)
  await page.goto(base + '/', { waitUntil: 'networkidle0', timeout: 60000 });
  const landing = await page.evaluate(() => document.body.innerText);
  check('Landing page explains the product and shows the live backend', landing.includes('Evidence-Seeking Federated Network Diagnosis') && landing.includes('Backend online'));
  await page.goto(base + '/command', { waitUntil: 'networkidle0', timeout: 60000 });
  await page.waitForFunction(() => document.body.innerText.includes('CONNECTED API'), { timeout: 20000 });
  check('UI shows CONNECTED API (live backend, not preview)', true);
  const agents = await api('/api/agents');
  check('3 specialist agents available over A2A', agents.agents.filter((a) => a.status === 'available' && a.transport === 'a2a').length === 3,
    agents.agents.map((a) => `${a.agent_id}:${a.status}/${a.transport}`).join(', '));

  // 2. Select S19 in the sidebar launcher and run
  await page.waitForSelector('select[aria-label="Scenario to run"] option[value="' + SCENARIO + '"]');
  await page.select('select[aria-label="Scenario to run"]', SCENARIO);
  const run = await page.waitForSelector('xpath/.//aside//button[contains(., "Run diagnosis")]');
  await run.click();
  await page.waitForFunction(() => JSON.parse(localStorage.getItem('netcoop-ui-v2') || '{}').state?.activeIncidentId, { timeout: 30000 });
  incidentId = await page.evaluate(() => JSON.parse(localStorage.getItem('netcoop-ui-v2')).state.activeIncidentId);
  let inc = await api(`/api/incidents/${incidentId}`);
  check('Run diagnosis created a new S19 incident on the backend', inc.incident.scenario_id === SCENARIO, incidentId);
  await page.screenshot({ path: `${outDir}/1-running.png` });

  // 3. Follow the live run to a terminal state
  await page.waitForFunction(() => /Diagnosed|Ambiguous|Insufficient|Failed/.test(document.querySelector('.hero')?.textContent ?? ''), { timeout: 120000 });
  await sleep(1500);
  check('UI opened the SSE stream for the incident', streamRequests.some((u) => u.includes(`/api/incidents/${incidentId}/stream`)), `${streamRequests.length} stream request(s)`);
  Object.assign(inc, await api(`/api/incidents/${incidentId}`));
  const report = await api(`/api/incidents/${incidentId}/report`);
  const tl = await api(`/api/incidents/${incidentId}/timeline`);
  await page.screenshot({ path: `${outDir}/2-command-center.png`, fullPage: true });
  const ccText = await page.evaluate(() => document.querySelector('.flow')?.textContent ?? '');
  check('Command Center flow shows the verification request to the infrastructure agent',
    ccText.includes('ASKED TO VERIFY') && ccText.includes('device_status') && ccText.includes('AP-2-1') && ccText.includes('DEVICE_DOWN'));

  // 4. Initial ambiguity + verification challenge (backend truth), and that the UI shows it
  const rounds = tl.events.filter((e) => e.state === 'CORRELATING' && e.run_id === inc.workflow?.run_id);
  const firstRound = rounds[0]?.detail ?? {};
  check('Backend: first correlation round was ambiguous (AP down vs port failure)', firstRound.status === 'ambiguous' &&
    (firstRound.competitors ?? []).some((h) => h.includes('DEVICE_DOWN-AP-2-1')),
    `round 0 status=${firstRound.status}; competitors=${(firstRound.competitors ?? []).join(' vs ')}`);
  const ch = (tl.challenges ?? []).find((c) => c.challenge.target_agent_id === 'infrastructure-agent' && c.challenge.requested_observation?.metric === 'device_status' && c.run_id === inc.workflow?.run_id);
  const subj = ch ? JSON.stringify(ch.challenge.requested_observation.subject) : '';
  check('Backend: challenge to infrastructure-agent for device_status of AP-2-1', ch && subj.includes('AP-2-1'), ch ? `${ch.challenge.challenge_id} ${subj}` : 'none');
  const outcome = ch?.outcomes?.[ch.outcomes.length - 1];
  check('Backend: challenge returned archived observations', outcome?.outcome === 'obtained' && outcome.detail?.new_observation_ids?.length > 0,
    outcome ? `${outcome.outcome}, ${outcome.detail?.new_observation_ids?.length} observation(s)` : 'no outcome');
  const verifyAttempt = tl.attempts.find((a) => a.task_type === 'verify' && a.agent_id === 'infrastructure-agent' && a.run_id === inc.workflow?.run_id);
  check('Backend: verify task went over A2A', verifyAttempt?.detail?.a2a_task_id, verifyAttempt?.detail?.a2a_task_id ?? 'no a2a task id');

  await page.goto(base + '/agents', { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => document.body.innerText.includes('QUERY'), { timeout: 15000 });
  const agentsText = await page.evaluate(() => document.body.innerText);
  check('UI timeline shows the QUERY to Infrastructure for device_status@AP-2-1',
    /QUERY/.test(agentsText) && agentsText.includes('device_status') && agentsText.includes('AP-2-1') && agentsText.includes('Infrastructure'));
  check('UI timeline shows the RESPONSE with returned observations', /RESPONSE/.test(agentsText));
  await page.screenshot({ path: `${outDir}/3-agent-timeline.png`, fullPage: true });

  // 5. Final result
  const cause = report.root_causes?.[0];
  check('Backend: DEVICE_DOWN at AP-2-1 with high_support',
    report.status === 'diagnosed' && cause?.fault_type === 'DEVICE_DOWN' && cause?.location === 'AP-2-1' && report.confidence_category === 'high_support',
    `${report.status} ${cause?.fault_type}@${cause?.location} ${report.confidence_category}`);
  await page.goto(base + '/reasoning', { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => document.body.innerText.includes('Targeted verification'));
  const rText = await page.evaluate(() => document.body.innerText);
  check('UI reasoning page shows the obtained verification check', rText.includes('obtained') && rText.includes('device_status'));
  await page.screenshot({ path: `${outDir}/4-reasoning.png`, fullPage: true });

  await page.goto(base + '/report', { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => document.body.innerText.includes('Device down at AP-2-1'), { timeout: 15000 });
  const repText = await page.evaluate(() => document.body.innerText);
  check('UI report shows "Device down at AP-2-1" and High support', repText.includes('Device down at AP-2-1') && repText.includes('High support'));
  check('UI never renders the support category as a percentage', !/\d+(\.\d+)?\s?%\s*(support|confidence)/i.test(repText));
  await page.screenshot({ path: `${outDir}/5-report.png`, fullPage: true });

  // 6. Export JSON and compare with the API
  const exp = await page.waitForSelector('xpath/.//button[contains(., "Export JSON")]');
  await exp.click();
  const fname = `${incidentId}-r${report.revision}.json`;
  for (let i = 0; i < 40 && !existsSync(`${dlDir}/${fname}`); i++) await sleep(250);
  const exported = existsSync(`${dlDir}/${fname}`) ? JSON.parse(readFileSync(`${dlDir}/${fname}`, 'utf8')) : null;
  if (exported) writeFileSync(`${outDir}/exported-report.json`, JSON.stringify(exported, null, 2)); // Chrome removes downloads on close
  check('Exported report JSON equals the backend report', exported && JSON.stringify(exported) === JSON.stringify(report),
    exported ? fname : `not downloaded (dir: ${readdirSync(dlDir).join(', ')})`);
} catch (e) {
  check('Unexpected error', false, e.message);
} finally {
  await browser.close();
}
check('No browser errors', errors.length === 0, errors.slice(0, 5).join(' | '));
const passed = steps.every((s) => s.ok);
writeFileSync(`${outDir}/result.json`, JSON.stringify({ scenario: SCENARIO, incident_id: incidentId, ran_at: new Date().toISOString(), ui: base, passed, steps }, null, 2));
console.log(passed ? `\nE2E S19: ALL ${steps.length} CHECKS PASSED` : `\nE2E S19: FAILED`);
process.exitCode = passed ? 0 : 1;

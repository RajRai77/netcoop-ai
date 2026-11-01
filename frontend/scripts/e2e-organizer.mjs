// End-to-end browser test on the organizer's sample-generator data against a REAL running backend.
//   node scripts/e2e-organizer.mjs [uiBaseUrl] [outDir]
// Runs ORG-03 (hardware failure on SW_CAMPUS_3) from the sidebar launcher and checks the UI against the
// backend's own responses: data-source label, ingestion warnings for undefined generator fields,
// localization, and that the calibrated confidence shown equals the report's value and basis.
import puppeteer from 'puppeteer-core';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const [base = 'http://127.0.0.1:5173', out = 'docs/e2e-organizer'] = process.argv.slice(2);
const SCENARIO = 'ORG-03-hardware-failure';
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium'].find((p) => existsSync(p));
const outDir = resolve(out);
mkdirSync(outDir, { recursive: true });
const steps = [];
const check = (name, ok, detail = '') => { steps.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`); };
const api = async (p) => { const r = await fetch(base + p); if (!r.ok) throw new Error(`${p}: HTTP ${r.status}`); return r.json(); };

const browser = await puppeteer.launch({ executablePath: chrome, headless: true });
const errors = [];
let incidentId = null;
try {
  const page = await browser.newPage();
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => m.type() === 'error' && errors.push(`console: ${m.text()}`));
  await page.setViewport({ width: 1920, height: 1080 });
  await page.evaluateOnNewDocument(() => {
    if (!sessionStorage.getItem('e2e-init')) {
      sessionStorage.setItem('e2e-init', '1');
      localStorage.setItem('netcoop-ui-v2', JSON.stringify({ state: { apiBase: '', apiToken: '', preview: false, reducedMotion: true,
        activeIncidentId: null, selectedScenarioId: null }, version: 0 }));
    }
  });
  const sc = (await api('/api/scenarios')).scenarios.find((s) => s.scenario_id === SCENARIO);
  check('Backend lists the organizer scenario with its declared profile', sc && sc.split === 'organizer' && sc.telemetry_profile === 'organizer-colab-json');
  await page.goto(base + '/command', { waitUntil: 'networkidle0', timeout: 60000 });
  const firstOption = await page.$eval('select[aria-label="Scenario to run"]', (s) => s.options[0]?.value);
  check('Organizer data is the first choice in the launcher', firstOption?.startsWith('ORG-'), firstOption);
  await page.select('select[aria-label="Scenario to run"]', SCENARIO);
  await (await page.waitForSelector('xpath/.//aside//button[contains(., "Run diagnosis")]')).click();
  await page.waitForFunction(() => JSON.parse(localStorage.getItem('netcoop-ui-v2') || '{}').state?.activeIncidentId, { timeout: 30000 });
  incidentId = await page.evaluate(() => JSON.parse(localStorage.getItem('netcoop-ui-v2')).state.activeIncidentId);
  await page.waitForFunction(() => /Diagnosed|Ambiguous|Insufficient|Unknown fault|Healthy/.test(document.querySelector('.hero')?.textContent ?? ''), { timeout: 120000 });
  await new Promise((r) => setTimeout(r, 1500));
  const report = await api(`/api/incidents/${incidentId}/report`);
  const evidence = await api(`/api/incidents/${incidentId}/evidence?limit=1`);
  const text = await page.evaluate(() => document.body.innerText);
  check('UI labels the data source as organizer data', text.includes('Organizer data · PS sample generator'));
  check('Backend localizes the fault to SW_CAMPUS_3', report.affected_devices.includes('SW_CAMPUS_3') &&
    (report.root_causes ?? []).every((c) => c.location.startsWith('SW_CAMPUS_3')), `${report.status} ${report.suspected_root_cause}`);
  check('Report carries a calibrated confidence with its basis', typeof report.confidence === 'number' && report.confidence_basis?.method === 'empirical_heldout',
    `${report.confidence} from ${report.confidence_basis?.correct}/${report.confidence_basis?.n} on ${report.confidence_basis?.set}`);
  check('UI shows exactly the report confidence', text.includes(`Confidence ${report.confidence.toFixed(2)}`));
  check('Undefined generator fields are reported, not used', (evidence.issues ?? []).some((i) => i.code === 'UNMAPPED_FIELD' && i.message.includes('metrics.queue_drops')));
  check('Support category is never rendered as a percentage', !/\d+(\.\d+)?\s?%\s*(support|confidence)/i.test(text));
  await page.screenshot({ path: `${outDir}/1-command-center.png`, fullPage: true });
  await page.goto(base + '/report', { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => document.body.innerText.includes('calibrated confidence'), { timeout: 15000 });
  await page.screenshot({ path: `${outDir}/2-report.png`, fullPage: true });
  check('Report page shows the calibrated-confidence block', true);
} catch (e) {
  check('Unexpected error', false, e.message);
} finally {
  await browser.close();
}
check('No browser errors', errors.length === 0, errors.slice(0, 5).join(' | '));
const passed = steps.every((s) => s.ok);
writeFileSync(`${outDir}/result.json`, JSON.stringify({ scenario: SCENARIO, incident_id: incidentId, ran_at: new Date().toISOString(), ui: base, passed, steps }, null, 2));
console.log(passed ? `\nE2E ORGANIZER: ALL ${steps.length} CHECKS PASSED` : '\nE2E ORGANIZER: FAILED');
process.exitCode = passed ? 0 : 1;

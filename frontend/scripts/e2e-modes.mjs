// Checks the two non-live modes in a real browser:
//  * preview: recorded data, labeled PREVIEW on every page, writes disabled, no request to a backend API
//  * offline: backend unreachable -> explicit "Backend offline" state, no fabricated data
//   node scripts/e2e-modes.mjs [uiBaseUrl] [outDir]
import puppeteer from 'puppeteer-core';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';

const [base = 'http://127.0.0.1:5173', out = 'docs/e2e-modes'] = process.argv.slice(2);
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium'].find((p) => existsSync(p));
mkdirSync(out, { recursive: true });
const ROUTES = ['/', '/incidents', '/topology', '/agents', '/evidence', '/reasoning', '/report', '/scenarios', '/evaluation', '/settings'];
const steps = [];
const check = (name, ok, detail = '') => { steps.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`); };
const browser = await puppeteer.launch({ executablePath: chrome, headless: true });

async function open(state, route) {
  const page = await browser.newPage();
  const apiCalls = [];
  const errors = [];
  page.on('request', (r) => {
    const p = new URL(r.url()).pathname;
    if (p.startsWith('/api/') || p.startsWith('/health/')) apiCalls.push(p);
  });
  page.on('pageerror', (e) => errors.push(e.message));
  await page.setViewport({ width: 1536, height: 960 });
  await page.evaluateOnNewDocument((s) => localStorage.setItem('netcoop-ui-v2', JSON.stringify({ state: s, version: 0 })), state);
  await page.goto(base + route, { waitUntil: 'networkidle0', timeout: 60000 });
  await new Promise((r) => setTimeout(r, 800));
  return { page, apiCalls, errors, text: await page.evaluate(() => document.body.innerText) };
}

try {
  const preview = { apiBase: '', apiToken: '', preview: true, reducedMotion: true, activeIncidentId: 'INC-b2e30992c4e04543', selectedScenarioId: 'S19-ap-down-status-in-archive' };
  for (const route of ROUTES) {
    const { page, apiCalls, errors, text } = await open(preview, route);
    const runDisabled = await page.evaluate(() => [...document.querySelectorAll('button')].find((b) => b.textContent?.includes('Run diagnosis'))?.disabled);
    check(`preview ${route}: labeled PREVIEW, writes disabled, no backend calls, no errors`,
      text.includes('PREVIEW') && text.includes('recorded') && runDisabled === true && apiCalls.length === 0 && errors.length === 0,
      `api calls=${apiCalls.length}${apiCalls.length ? ' ' + apiCalls.join(',') : ''} errors=${errors.length} runDisabled=${runDisabled}`);
    if (route === '/' || route === '/evaluation') await page.screenshot({ path: `${out}/preview${route === '/' ? '-command-center' : route.replace('/', '-')}.png` });
    await page.close();
  }
  const offline = { ...preview, preview: false, apiBase: 'http://127.0.0.1:9' };
  for (const route of ['/', '/report', '/evaluation']) {
    const { page, text, errors } = await open(offline, route);
    check(`offline ${route}: explicit backend-offline state, no diagnosis shown`,
      /Backend offline/i.test(text) && !text.includes('Device down at AP-2-1') && errors.length === 0, `errors=${errors.length}`);
    if (route === '/') await page.screenshot({ path: `${out}/offline-command-center.png` });
    await page.close();
  }
} catch (e) {
  check('Unexpected error', false, e.message);
} finally {
  await browser.close();
}
const passed = steps.every((s) => s.ok);
writeFileSync(`${out}/result.json`, JSON.stringify({ ran_at: new Date().toISOString(), ui: base, passed, steps }, null, 2));
console.log(passed ? `\nMODES: ALL ${steps.length} CHECKS PASSED` : '\nMODES: FAILED');
process.exitCode = passed ? 0 : 1;

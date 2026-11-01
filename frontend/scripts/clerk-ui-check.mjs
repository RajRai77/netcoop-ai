// Browser checks of a Clerk-mode build WITHOUT a live Clerk instance (signed-out / sign-in-unavailable paths).
//   node scripts/clerk-ui-check.mjs <baseUrl of an app built with VITE_CLERK_PUBLISHABLE_KEY>
// A live Google sign-in needs the owner's real Clerk instance; this verifies everything a signed-out visitor sees:
// public landing, sign-in CTAs, protected routes gated (no API calls to incident endpoints, no 401 walls),
// no token field anywhere, and the "unable to verify your session" state when Clerk cannot load.
import puppeteer from 'puppeteer-core';
import { existsSync } from 'node:fs';

const base = process.argv[2] ?? 'http://127.0.0.1:8030';
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', '/usr/bin/google-chrome', '/usr/bin/chromium'].find((p) => existsSync(p));
const steps = [];
const check = (name, ok, detail = '') => { steps.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`); };
const browser = await puppeteer.launch({ executablePath: chrome, headless: true });
try {
  const page = await browser.newPage();
  const calls = [];
  page.on('request', (r) => { const p = new URL(r.url()).pathname; if (p.startsWith('/api/')) calls.push(p); });
  await page.setViewport({ width: 1440, height: 900 });
  await page.goto(base + '/', { waitUntil: 'networkidle2', timeout: 60000 });
  const landing = await page.evaluate(() => document.body.innerText);
  check('Landing page is public', landing.includes('Evidence-Seeking Federated Network Diagnosis'));
  check('Sign-in CTAs are shown to signed-out visitors', /Continue with Google|Loading sign-in/.test(landing) && /Sign in|Loading sign-in/.test(landing));
  check('Landing calls only public catalog endpoints', calls.every((p) => /^\/api\/(meta|agents|evaluations)/.test(p)), [...new Set(calls)].join(', '));
  for (const route of ['/command', '/report', '/settings', '/scenarios']) {
    calls.length = 0;
    await page.goto(base + route, { waitUntil: 'networkidle2', timeout: 60000 });
    const t = await page.evaluate(() => document.body.innerText);
    const incidentCalls = calls.filter((p) => p.startsWith('/api/incidents') || p.startsWith('/api/raw-records'));
    check(`${route}: gated, no incident API calls, no 401 wall, no token field`,
      /Checking your session|Sign in to start investigating|Unable to verify your session/.test(t) && incidentCalls.length === 0
      && !/Unauthorized|API token/i.test(t) && !(await page.$('input[type="password"]')), incidentCalls.join(', '));
  }
  await page.goto(base + '/command', { waitUntil: 'networkidle2' });
  await page.waitForFunction(() => document.body.innerText.includes('Unable to verify your session'), { timeout: 25000 });
  check('Unreachable sign-in service shows "Unable to verify your session" with a reload action', true);
} catch (e) {
  check('Unexpected error', false, e.message);
} finally {
  await browser.close();
}
const ok = steps.every(Boolean);
console.log(ok ? `\nCLERK UI: ALL ${steps.length} CHECKS PASSED` : '\nCLERK UI: FAILED');
process.exitCode = ok ? 0 : 1;

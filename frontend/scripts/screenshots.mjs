// Real-browser screenshots of the running UI (installed Chrome via puppeteer-core).
//   node scripts/screenshots.mjs <baseUrl> <incidentId> <outDir> [route ...]
import puppeteer from 'puppeteer-core';
import { mkdirSync, existsSync } from 'node:fs';

const [base = 'http://127.0.0.1:5173', incident = '', out = 'docs/screenshots', ...routes] = process.argv.slice(2);
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium'].find((p) => existsSync(p));
if (!chrome) throw new Error('No Chrome/Edge found');
mkdirSync(out, { recursive: true });
const viewports = [
  ['1920x1080', 1920, 1080, 1], ['1536x960', 1536, 960, 1], ['1366x768', 1366, 768, 1], ['mobile-390x844', 390, 844, 2],
];
const browser = await puppeteer.launch({ executablePath: chrome, headless: true, args: ['--force-color-profile=srgb'] });
const errors = [];
try {
  for (const route of routes.length ? routes : ['/']) {
    for (const [name, w, h, dpr] of viewports) {
      const page = await browser.newPage();
      page.on('pageerror', (e) => errors.push(`${route} ${name}: ${e.message}`));
      page.on('console', (m) => m.type() === 'error' && errors.push(`${route} ${name} console: ${m.text()}`));
      await page.setViewport({ width: w, height: h, deviceScaleFactor: dpr });
      await page.evaluateOnNewDocument((id) => {
        localStorage.setItem('netcoop-ui-v2', JSON.stringify({ state: { apiBase: '', apiToken: '', preview: false, reducedMotion: false,
          activeIncidentId: id || null, selectedScenarioId: 'S19-ap-down-status-in-archive' }, version: 0 }));
      }, incident);
      await page.goto(base + route, { waitUntil: 'networkidle0', timeout: 60000 });
      await new Promise((r) => setTimeout(r, 1500)); // React Flow fitView + fonts
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      const file = `${out}/${route === '/' ? 'command-center' : route.replace(/\W+/g, '')}-${name}.png`;
      await page.screenshot({ path: file, fullPage: name === '1920x1080' || name.startsWith('mobile') });
      console.log(`${file}  horizontal-overflow=${overflow}px`);
      await page.close();
    }
  }
} finally {
  await browser.close();
}
if (errors.length) { console.log('BROWSER ERRORS:\n' + errors.join('\n')); process.exitCode = 1; }

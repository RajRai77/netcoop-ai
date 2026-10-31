// Basic automated accessibility checks on every route (not a substitute for an axe/WCAG audit):
// controls have accessible names, form fields are labeled, images have alt, a page heading exists,
// and Tab moves focus to a visible element.
//   node scripts/a11y-check.mjs [uiBaseUrl] [incidentId]
import puppeteer from 'puppeteer-core';
import { existsSync } from 'node:fs';

const [base = 'http://127.0.0.1:5173', incident = 'INC-b2e30992c4e04543'] = process.argv.slice(2);
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', '/usr/bin/google-chrome', '/usr/bin/chromium'].find((p) => existsSync(p));
const ROUTES = ['/', '/incidents', '/topology', '/agents', '/evidence', '/reasoning', '/report', '/scenarios', '/evaluation', '/settings'];
const browser = await puppeteer.launch({ executablePath: chrome, headless: true });
let failures = 0;
try {
  for (const route of ROUTES) {
    const page = await browser.newPage();
    await page.setViewport({ width: 1536, height: 960 });
    await page.evaluateOnNewDocument((id) => localStorage.setItem('netcoop-ui-v2', JSON.stringify({ state: { apiBase: '', apiToken: '', preview: false,
      reducedMotion: true, activeIncidentId: id, selectedScenarioId: 'S19-ap-down-status-in-archive' }, version: 0 })), incident);
    await page.goto(base + route, { waitUntil: 'networkidle0', timeout: 60000 });
    await new Promise((r) => setTimeout(r, 800));
    const res = await page.evaluate(() => {
      const name = (el) => (el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent || '').trim();
      const unnamed = [...document.querySelectorAll('button, a[href], [role="button"]')].filter((el) => !name(el) && !el.closest('.react-flow__attribution'))
        .map((el) => el.outerHTML.slice(0, 90));
      const unlabeled = [...document.querySelectorAll('input:not([type=hidden]), select, textarea')].filter((el) =>
        !el.hidden && !el.getAttribute('aria-label') && !el.closest('label') && !(el.id && document.querySelector(`label[for="${el.id}"]`)))
        .map((el) => el.outerHTML.slice(0, 90));
      const noAlt = [...document.querySelectorAll('img')].filter((i) => !i.hasAttribute('alt')).length;
      const headings = document.querySelectorAll('h1, h2').length;
      return { unnamed, unlabeled, noAlt, headings, lang: document.documentElement.lang };
    });
    await page.keyboard.press('Tab');
    const focus = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      const s = getComputedStyle(el);
      return { tag: el.tagName, outline: s.outlineStyle !== 'none' || s.boxShadow !== 'none' };
    });
    const ok = !res.unnamed.length && !res.unlabeled.length && !res.noAlt && res.headings > 0 && !!res.lang && !!focus;
    if (!ok) failures++;
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${route}  headings=${res.headings} lang=${res.lang} focus=${focus ? focus.tag + (focus.outline ? '+ring' : '') : 'none'}` +
      (res.unnamed.length ? `\n   unnamed controls: ${res.unnamed.join(' | ')}` : '') + (res.unlabeled.length ? `\n   unlabeled fields: ${res.unlabeled.join(' | ')}` : '') +
      (res.noAlt ? `\n   images without alt: ${res.noAlt}` : ''));
    await page.close();
  }
} finally {
  await browser.close();
}
console.log(failures ? `\nA11Y: ${failures} route(s) failed` : '\nA11Y: all routes passed the basic checks');
process.exitCode = failures ? 1 : 0;

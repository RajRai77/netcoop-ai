// Records the narrated product demo against the REAL running app (no mock data).
//   node scripts/demo/record-demo.mjs <uiBaseUrl> <workDir> <ffmpegPath>
// workDir must contain audio/<step>.wav (scripts/demo/tts.ps1). Writes workDir/frames/*.jpg + frames.json and timeline.json
// (start/end of every narration step, used by build-video.mjs for the audio track and the .srt file).
// Subtitles are rendered in the page (burned into the video); a pointer shows where the viewer should look.
import puppeteer from 'puppeteer-core';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const [base = 'http://127.0.0.1:5173', work, ffmpegPath] = process.argv.slice(2);
const here = dirname(fileURLToPath(import.meta.url));
const steps = JSON.parse(readFileSync(join(here, 'narration.json'), 'utf8'));
function wavSeconds(f) {  // walk RIFF chunks: fmt may be 16 or 18 bytes, so offsets are not fixed
  const b = readFileSync(f);
  let off = 12, byteRate = 0;
  while (off + 8 <= b.length) {
    const id = b.toString('ascii', off, off + 4), size = b.readUInt32LE(off + 4);
    if (id === 'fmt ') byteRate = b.readUInt32LE(off + 16);
    if (id === 'data') return size / byteRate;
    off += 8 + size + (size % 2);
  }
  throw new Error(`no data chunk in ${f}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const chrome = 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const browser = await puppeteer.launch({ executablePath: chrome, headless: true, args: ['--hide-scrollbars'] });
const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080 });
await page.evaluateOnNewDocument(() => {
  localStorage.setItem('netcoop-ui-v2', JSON.stringify({ state: { apiBase: '', apiToken: '', preview: false, reducedMotion: false,
    activeIncidentId: null, selectedScenarioId: 'ORG-03-hardware-failure' }, version: 0 }));
  const css = `#demo-cap{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:2147483646;max-width:1480px;
    padding:12px 22px 14px;border-radius:14px;background:rgba(7,16,36,.97);backdrop-filter:blur(6px);color:#fff;font:600 25px/1.38 'Inter Variable',Inter,system-ui,sans-serif;
    text-align:center;box-shadow:0 10px 30px rgba(0,0,0,.35);transition:opacity .25s}
    #demo-cap small{display:block;font:700 13px/1.4 'Inter Variable',Inter,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:#39ff88;margin-bottom:4px}
    #demo-ptr{position:fixed;z-index:2147483647;left:960px;top:540px;width:38px;height:38px;margin:-19px 0 0 -19px;border-radius:50%;
    border:4px solid #ff7a00;background:rgba(255,122,0,.22);box-shadow:0 0 0 7px rgba(255,122,0,.18),0 4px 14px rgba(0,0,0,.3);pointer-events:none;
    transition:left .7s cubic-bezier(.4,0,.2,1),top .7s cubic-bezier(.4,0,.2,1),transform .15s}
    #demo-ptr.down{transform:scale(.7)}`;
  const mount = () => {
    if (document.getElementById('demo-cap')) return;
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    const cap = document.createElement('div'); cap.id = 'demo-cap'; cap.style.opacity = '0'; document.body.appendChild(cap);
    const ptr = document.createElement('div'); ptr.id = 'demo-ptr'; document.body.appendChild(ptr);
  };
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', mount) : mount();
  window.__cap = (chapter, text) => { mount(); const c = document.getElementById('demo-cap'); c.innerHTML = `<small>${chapter}</small>${text}`; c.style.opacity = '1'; };
});

// ---------- helpers ----------
async function el(sel, text) {
  const h = await page.waitForFunction((sel, text) => {
    const list = [...document.querySelectorAll(sel)].filter((e) => e.offsetParent !== null || e.getClientRects().length);
    return (text ? list.find((e) => e.textContent.includes(text)) : list[0]) ?? null;
  }, { timeout: 30000 }, sel, text ?? null);
  return h.asElement();
}
async function center(h) {
  return page.evaluate((e) => { const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }, h);
}
async function point(sel, text) {
  const h = await el(sel, text);
  const c = await center(h);
  await page.evaluate(({ x, y }) => { const p = document.getElementById('demo-ptr'); p.style.left = x + 'px'; p.style.top = y + 'px'; }, c);
  await sleep(750);
  return h;
}
async function click(sel, text) {
  const h = await point(sel, text);
  await page.evaluate(() => document.getElementById('demo-ptr').classList.add('down'));
  await sleep(150);
  await h.click();
  await page.evaluate(() => document.getElementById('demo-ptr').classList.remove('down'));
  await sleep(300);
}
async function show(sel, text, block = 'center') {
  const h = await el(sel, text);
  await page.evaluate((e, block) => e.scrollIntoView({ behavior: 'smooth', block }), h, block);
  await sleep(900);
}
const top = async () => { await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' })); await sleep(800); };
const nav = (label) => click('nav.nav a', label);
async function runScenario(id, titleHas) {
  await page.select('select[aria-label="Scenario to run"]', id);
  await sleep(500);
  await click('aside button', 'Run diagnosis');
  await page.waitForFunction((t) => (document.querySelector('.hero h1')?.textContent ?? '').includes(t), { timeout: 60000 }, titleHas);
  await page.waitForFunction(() => /Diagnosed|Ambiguous|Unknown fault|Insufficient|Healthy/.test(document.querySelector('.hero')?.textContent ?? '')
    && !document.querySelector('.hero')?.textContent.includes('In progress'), { timeout: 180000 });
  await sleep(1200);
}
const tour = async (sels, ms) => { for (const [s, t] of sels) { await point(s, t); await sleep(ms); } };

// ---------- the actions for each narration step ----------
const ACTIONS = {
  intro1: async () => { await point('.l-hero h1'); },
  intro2: async () => { await point('.l-panel'); },
  why: async () => { await show('#why', null, 'start'); await point('.l-problem.bad'); },
  approach: async () => { await point('.l-problem.good'); await sleep(2500); await show('.l-grid.g5'); await point('.l-grid.g5 .l-card', 'Verification before'); },
  how: async () => { await show('#how', null, 'start'); await tour([['.l-how', 'Telemetry arrives'], ['.l-how', 'STEaR builds'], ['.l-how', 'Missing evidence']], 900); },
  results: async () => { await show('#evidence', null, 'start'); await point('.l-bench .best'); await sleep(2500); await point('.l-bench .l-card', 'Threshold'); },
  open: async () => { await top(); await click('.l-ctas a', 'Explore Command Center'); await el('.hero'); },
  sidebar: async () => { await point('.nav'); await sleep(2500); await point('.side-foot'); },
  pickorg: async () => { await point('select[aria-label="Scenario to run"]'); await page.select('select[aria-label="Scenario to run"]', 'ORG-03-hardware-failure'); },
  runorg: async () => { await runScenario('ORG-03-hardware-failure', 'SW_CAMPUS_3'); },
  label: async () => { await top(); await point('.hero-meta .chip', 'Organizer data'); },
  unmapped: async () => { await point('.hero .panel-sub', 'unused'); },
  flow1: async () => { await show('.flow'); await point('.flow .fnode', 'Incident'); },
  flow2: async () => { await tour([['.flow .fnode', 'Performance Agent'], ['.flow .fnode', 'Infrastructure Agent'], ['.flow .fnode', 'Connectivity']], 2300); },
  flow3: async () => { await point('.flow .fnode', 'STEaR Reasoner'); await sleep(2000); await point('.flow .fnode', 'Verification check'); },
  final1: async () => { await point('.flow .fnode.final'); },
  conf: async () => { await top(); await point('.kpi .chip', 'Confidence'); },
  topo1: async () => { await show('.panel', 'Network topology'); await point('.tnode.cause'); },
  lower: async () => { await show('.row.triple', null, 'start'); await tour([['.row.triple .panel', 'Investigation timeline'], ['.why'], ['.final-box']], 1800); },
  picks19: async () => { await top(); await point('select[aria-label="Scenario to run"]'); await page.select('select[aria-label="Scenario to run"]', 'S19-ap-down-status-in-archive'); },
  runs19: async () => { await runScenario('S19-ap-down-status-in-archive', 'AP-2-1'); },
  tie: async () => { await show('.flow'); await point('.flow .fnode', 'STEaR Reasoner'); await sleep(1500); await point('.flow .panel-sub, .flow ~ .panel-sub, .panel-sub', 'Round 1 tie'); },
  ask: async () => { await point('.flow .fnode', 'Verification check'); await sleep(2500); await point('.flow .fnode-badge', 'ASKED TO VERIFY'); },
  answer: async () => { await point('.flow .fnode', 'Verification check'); await sleep(2200); await point('.flow .fnode.final'); },
  topo2: async () => { await show('.panel', 'Network topology'); await point('.tnode.cause'); },
  agents1: async () => { await top(); await nav('Agent Collaboration'); await tour([['.panel', 'Performance'], ['.panel', 'Infrastructure'], ['.panel', 'Connectivity']], 1200); },
  agents2: async () => { await show('.tl'); await click('.tl-card', 'new findings'); await sleep(1500);
    await page.evaluate(() => document.querySelector('.drawer-body')?.scrollBy({ top: 500, behavior: 'smooth' })); await sleep(4000); await page.keyboard.press('Escape'); },
  reason1: async () => { await nav('STEaR Reasoning'); await point('.panel', 'Decision basis'); await sleep(2500); await point('.story'); },
  reason2: async () => { await show('.panel', 'All hypotheses', 'start'); await point('.hyp'); },
  ev1: async () => { await top(); await nav('Evidence Explorer'); await point('table.t'); },
  ev2: async () => { await click('table.t tbody tr.click'); await sleep(1500);
    await page.evaluate(() => document.querySelector('.drawer-body')?.scrollBy({ top: 900, behavior: 'smooth' })); await sleep(3500); await page.keyboard.press('Escape'); },
  data1: async () => { await nav('Datasets & Upload'); await point('.panel', 'Scenario library'); await sleep(2000); await show('#upload'); await point('.drop'); },
  drift1: async () => { await top(); await show('.hyp', 'ORG-04-schema-drift'); await point('.hyp', 'ORG-04-schema-drift');
    const card = await el('.hyp', 'ORG-04-schema-drift'); const btn = await card.$('button');
    const c = await center(btn); await page.evaluate(({ x, y }) => { const p = document.getElementById('demo-ptr'); p.style.left = x + 'px'; p.style.top = y + 'px'; }, c);
    await sleep(800); await btn.click();
    await page.waitForFunction(() => (document.querySelector('.hero h1')?.textContent ?? '').includes('schema drift'), { timeout: 60000 });
    await page.waitForFunction(() => /Unknown fault|Diagnosed|Ambiguous|Insufficient/.test(document.querySelector('.hero')?.textContent ?? '')
      && !document.querySelector('.hero')?.textContent.includes('In progress'), { timeout: 180000 }); },
  drift2: async () => { await nav('Evidence Explorer'); await click('.tabs button', 'Validation issues'); await point('table.t'); },
  rep1: async () => { await nav('Reports'); await point('.panel', 'Conclusion'); },
  rep2: async () => { await show('.panel', 'Limitations'); await point('.panel', 'Limitations'); },
  rep3: async () => { await top(); await click('.tabs button', 'JSON'); await sleep(1500); await point('button', 'Export JSON'); },
  eval1: async () => { await nav('Evaluation'); await point('.mode-banner'); },
  eval2: async () => { await show('table.t'); await point('table.t th', 'STEaR full'); await sleep(2000); await point('table.t td', '59/60'); },
  settings: async () => { await nav('Settings'); await point('.panel', 'Backend connection'); await sleep(2500); await point('.panel', 'Mode & display'); },
  run: async () => { await nav('Command Center'); await point('.side-foot'); },
  outro: async () => { await click('a.brand'); await sleep(600); await point('.l-hero h1'); },
};

console.log('loading app'); await page.goto(base + '/', { waitUntil: 'load', timeout: 60000 });
await page.waitForSelector('.l-hero h1', { timeout: 30000 });
await sleep(1500);
console.log('app loaded, starting recorder');
// Chrome's own JPEG screencast frames (cheap: no real-time video encoding competing with the agents for CPU).
// Frames are written with their capture timestamps and assembled by build-video.mjs.
mkdirSync(join(work, 'frames'), { recursive: true });
const frames = [];
const cdp = await page.createCDPSession();
cdp.on('Page.screencastFrame', ({ data, metadata, sessionId }) => {
  const name = `f${String(frames.length).padStart(6, '0')}.jpg`;
  writeFileSync(join(work, 'frames', name), Buffer.from(data, 'base64'));
  frames.push({ name, t: metadata.timestamp });
  cdp.send('Page.screencastFrameAck', { sessionId }).catch(() => {});
});
const t0 = Date.now();
await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 85, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
console.log('recording');
const timeline = [];
const only = Number(process.env.DEMO_STEPS || 0);
for (const s of only ? steps.slice(0, only) : steps) {
  const dur = wavSeconds(join(work, 'audio', `${s.id}.wav`));
  const start = (Date.now() - t0) / 1000;
  await page.evaluate((c, t) => window.__cap(c, t), s.chapter, s.text);
  const act = (ACTIONS[s.id] ?? (async () => {}))().catch((e) => console.log(`action ${s.id}: ${e.message}`));
  await Promise.all([act, sleep(dur * 1000 + 250)]);
  const end = (Date.now() - t0) / 1000;
  timeline.push({ id: s.id, chapter: s.chapter, text: s.text, start, end, audio: dur });
  console.log(`${start.toFixed(1).padStart(6)}s  ${s.id}`);
}
await sleep(1500);
await cdp.send('Page.stopScreencast');
const tEnd = Date.now() / 1000;
await browser.close();
writeFileSync(join(work, 'timeline.json'), JSON.stringify(timeline, null, 1));
writeFileSync(join(work, 'frames.json'), JSON.stringify({ t0: t0 / 1000, tEnd, frames }));
console.log(`recorded ${((Date.now() - t0) / 1000).toFixed(0)} s`);

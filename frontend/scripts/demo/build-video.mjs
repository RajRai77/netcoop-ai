// Assemble the final demo: narration clips placed at their recorded times + the screen recording.
//   node scripts/demo/build-video.mjs <workDir> <ffmpegPath> <outMp4>
// Writes <outMp4> (H.264 + AAC, subtitles burned in by the recorder and also embedded as a soft track) and
// <outMp4 without extension>.srt.
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const [work, ffmpeg, out] = process.argv.slice(2);
const tl = JSON.parse(readFileSync(join(work, 'timeline.json'), 'utf8'));
const ts = (s) => {
  const ms = Math.round(s * 1000);
  const p = (n, w = 2) => String(n).padStart(w, '0');
  return `${p(Math.floor(ms / 3600000))}:${p(Math.floor(ms / 60000) % 60)}:${p(Math.floor(ms / 1000) % 60)},${p(ms % 1000, 3)}`;
};
const srtPath = out.replace(/\.mp4$/i, '') + '.srt';
writeFileSync(srtPath, tl.map((c, i) => `${i + 1}\n${ts(c.start)} --> ${ts(c.end - 0.05)}\n${c.text}\n`).join('\n'), 'utf8');

const run = (args) => {
  const r = spawnSync(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', ...args], { stdio: 'inherit' });
  if (r.status !== 0) throw new Error(`ffmpeg failed (${r.status})`);
};
// 1) narration track
const inputs = tl.flatMap((c) => ['-i', join(work, 'audio', `${c.id}.wav`)]);
const delays = tl.map((c, i) => `[${i}:a]aresample=48000,adelay=${Math.round(c.start * 1000 + 150)}|${Math.round(c.start * 1000 + 150)}[a${i}]`);
const mix = `${delays.join(';')};${tl.map((_, i) => `[a${i}]`).join('')}amix=inputs=${tl.length}:normalize=0:dropout_transition=0,volume=1.25,alimiter=limit=0.95[aout]`;
run([...inputs, '-filter_complex', mix, '-map', '[aout]', '-ac', '2', join(work, 'narration.wav')]);
// 2) frames -> constant-rate video, each frame shown until the next one was captured
const fr = JSON.parse(readFileSync(join(work, 'frames.json'), 'utf8'));
const lines = [];
fr.frames.forEach((f, i) => {
  const start = Math.max(f.t, fr.t0);
  const next = i + 1 < fr.frames.length ? fr.frames[i + 1].t : fr.tEnd;
  if (i === 0 && f.t > fr.t0) { lines.push(`file 'frames/${f.name}'`, `duration ${(f.t - fr.t0).toFixed(3)}`); }
  lines.push(`file 'frames/${f.name}'`, `duration ${Math.max(0.001, next - start).toFixed(3)}`);
});
lines.push(`file 'frames/${fr.frames[fr.frames.length - 1].name}'`);
writeFileSync(join(work, 'frames.txt'), lines.join('\n') + '\n');
// 3) video + narration + soft subtitles
run(['-f', 'concat', '-safe', '0', '-i', join(work, 'frames.txt'), '-i', join(work, 'narration.wav'), '-i', srtPath,
  '-map', '0:v', '-map', '1:a', '-map', '2:s', '-c:v', 'libx264', '-preset', 'medium', '-crf', '24', 
  '-vf', 'fps=25,format=yuv420p', '-c:a', 'aac', '-b:a', '160k', '-c:s', 'mov_text', '-metadata:s:s:0', 'language=eng',
  '-movflags', '+faststart', '-shortest', out]);
console.log(`wrote ${out} and ${srtPath}`);

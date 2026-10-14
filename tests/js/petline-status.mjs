// Runs Petline's real status() (copied out of pets.html at test time) for the parity test.
//   node petline-status.mjs <pets.html> <cases.json>     cases: { pets, at: [ms…] } → prints { "<at>|<pet>|<task>": state }
// Run with TZ set (the test uses Europe/London) so the page's local-time maths matches the Python side.
import { readFileSync } from 'node:fs';

const [html, casesFile] = process.argv.slice(2);
const src = readFileSync(html, 'utf8');
const start = src.indexOf('const pad = n =>'), end = src.indexOf('const needs = s =>');
if (start < 0 || end < 0) throw new Error('status() not found in pets.html: update this test');
const cases = JSON.parse(readFileSync(casesFile, 'utf8'));

const RealDate = Date;
let fixed = 0;
globalThis.Date = class extends RealDate {
  constructor(...a){ if (a.length) super(...a); else super(fixed); }
  static now(){ return fixed; }
};
let pets = [];
const fns = new Function('getPets', `const KINDS = [], PRESETS = []; let pets; const logsOf = (p, task) => (p.log || []).filter(l => l.task === task.id).sort((a, b) => a.t - b.t);
  ${src.slice(start, end).replace(/^const (KINDS|PRESETS) = [\s\S]*?\]\];$/gm, '').replace(/^const (petOf|sel|logsOf) = .*$/gm, '')}
  return { status };`)(() => pets);
const out = {};
for (const at of cases.at){
  fixed = at;
  for (const p of cases.pets) for (const t of p.tasks) out[`${at}|${p.id}|${t.id}`] = fns.status(p, t, at).state;
}
console.log(JSON.stringify(out));

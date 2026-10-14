// Runs named functions copied out of an app's page, with the clock fixed, for the parity tests.
//   node app-fns.mjs <page.html> <spec.json>
//   spec: { names: ['pad', 'ymdOf', 'nextDate', …] (const one-liners or function declarations, in order), prelude: 'const opts = {…};',
//           calls: [{ at: ms, expr: 'nextDate({…})' }, …] }  → prints the results (JSON) in order.
// Run with TZ set (Europe/London) so the page's local-date maths matches the Python side.
import { readFileSync } from 'node:fs';

const [page, specFile] = process.argv.slice(2);
const src = readFileSync(page, 'utf8'), spec = JSON.parse(readFileSync(specFile, 'utf8'));
function grab(name){
  const fn = src.search(new RegExp(`\\nfunction ${name}\\(`));
  if (fn >= 0){
    let i = src.indexOf('{', src.indexOf(')', fn)), depth = 0, j = i;
    for (; j < src.length; j++){ const c = src[j]; if (c === '{') depth++; else if (c === '}' && --depth === 0) break; }
    return src.slice(fn + 1, j + 1);
  }
  const m = new RegExp(`\\nconst ${name} = [^\\n]*`).exec(src);
  if (m) return m[0].slice(1);
  throw new Error(`${name} not found in ${page}: update the test`);
}
const RealDate = Date;
let fixed = 0;
globalThis.Date = class extends RealDate { constructor(...a){ if (a.length) super(...a); else super(fixed); } static now(){ return fixed; } };
const body = (spec.prelude || '') + '\n' + spec.names.map(grab).join('\n') + '\nreturn (expr) => eval(expr);';
const run = new Function(body)();
const out = spec.calls.map(c => { fixed = c.at; try{ return run(c.expr); } catch(e){ return { error: String(e.message || e) }; } });
console.log(JSON.stringify(out));

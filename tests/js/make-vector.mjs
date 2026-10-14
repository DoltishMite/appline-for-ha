// Seal a JSON file exactly the way the kit does (kit.js HPCloudSync / tools/together.js), for the integration's Python tests.
//   node make-vector.mjs <in.json> <out.json> [--share] [--plain] [--code CODE]
// Writes { code, id, doc }: a fresh random test code (or --code), the /api/sync id, and the sealed document.
// --share: together-id:/together-key: (a shared thing) instead of sync-id:/sync-key:. --plain: no gzip ("p").
// Never pass a real sync or share code: tests only use codes made here.
import { readFileSync, writeFileSync } from 'node:fs';

const args = process.argv.slice(2), flag = f => args.includes(f);
const ci = args.indexOf('--code');
const [inFile, outFile] = args.filter((a, i) => !a.startsWith('--') && !(ci >= 0 && i === ci + 1));
if (!inFile || !outFile){ console.error('usage: node make-vector.mjs <in.json> <out.json> [--share] [--plain] [--code CODE]'); process.exit(2); }

const ALPHA = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
const norm = c => String(c || '').toUpperCase().replace(/[IL]/g, '1').replace(/O/g, '0').replace(/[^0-9A-Z]/g, '').split('').filter(ch => ALPHA.includes(ch)).join('');
const pretty = c => norm(c).match(/.{1,4}/g).join('-');
const code = ci >= 0 ? args[ci + 1] : pretty(Array.from(crypto.getRandomValues(new Uint8Array(20)), x => ALPHA[x & 31]).join(''));

const enc = new TextEncoder(), pre = flag('--share') ? 'together' : 'sync';
const hex = buf => Array.from(new Uint8Array(buf), b => b.toString(16).padStart(2, '0')).join('');
const b64 = u8 => { let s = ''; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(s); };
const pipe = async (u8, stream) => new Uint8Array(await new Response(new Blob([u8]).stream().pipeThrough(stream)).arrayBuffer());

const c = norm(code);
const id = hex(await crypto.subtle.digest('SHA-256', enc.encode(`${pre}-id:` + c)));
const key = await crypto.subtle.importKey('raw', await crypto.subtle.digest('SHA-256', enc.encode(`${pre}-key:` + c)), 'AES-GCM', false, ['encrypt']);

let u8 = enc.encode(JSON.stringify(JSON.parse(readFileSync(inFile, 'utf8')))), z = 'p';
if (!flag('--plain')){ u8 = await pipe(u8, new CompressionStream('gzip')); z = 'z'; }
const iv = crypto.getRandomValues(new Uint8Array(12));
const doc = `1.${z}.${b64(iv)}.${b64(new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, u8)))}`;

writeFileSync(outFile, JSON.stringify({ code, id, doc }, null, 2));
console.log(`sealed ${inFile} → ${outFile} (${pre}, ${z}, ${doc.length} chars)`);

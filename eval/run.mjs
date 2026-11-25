// Send the 20 test leads to one platform's webhook, then score what it wrote to its Sheet tab.
//   node eval/run.mjs --platform n8n|make|zapier --url <webhook URL> [--ids t01,t02] [--gap-ms 1500] [--wait-s 600]
//   node eval/run.mjs --platform zapier --rescore   # score the rows already in the tab; no leads sent, no latency
// Rows are matched by lead ID. Latency = row timestamp (written by the platform) minus send time.
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > -1 ? process.argv[i + 1] : d; };
const PLATFORM = arg('--platform'), URL_ = arg('--url'), IDS = arg('--ids', ''), RESCORE = process.argv.includes('--rescore');
const GAP = Number(arg('--gap-ms', 1500)), WAIT = Number(arg('--wait-s', 600));
if (!['n8n', 'make', 'zapier'].includes(PLATFORM) || !(URL_ || RESCORE)) throw new Error('need --platform and --url (or --rescore)');

const env = Object.fromEntries(readFileSync(join(ROOT, '.env'), 'utf8').split('\n').filter(l => l.includes('='))
  .map(l => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)]));
const TOKEN_FILE = process.env.GOOGLE_TOKEN_FILE;
if (!TOKEN_FILE) throw new Error('set GOOGLE_TOKEN_FILE (see scripts/google_token.py)');
const token = () => { execFileSync('python3', [join(ROOT, 'scripts/google_token.py'), TOKEN_FILE]); return readFileSync(TOKEN_FILE, 'utf8').trim(); };

const cases = readFileSync(join(ROOT, 'eval/leads.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l))
  .filter(c => !IDS || IDS.split(',').includes(c.lead.lead_id));

// 1. Send
const sent = {};
for (const c of RESCORE ? [] : cases) {
  sent[c.lead.lead_id] = Date.now();
  const r = await fetch(URL_, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(c.lead) });
  process.stderr.write(`sent ${c.lead.lead_id} -> ${r.status}\n`);
  await new Promise(res => setTimeout(res, GAP));
}

// 2. Wait for the rows
// Zapier's Sheets step rewrites the ISO timestamp as 'YYYY-MM-DD H:MM:SS' (UTC digits, no zone, no ms), and Sheets can
// show it as a date serial (days since 1899-12-30). Read both as UTC.
const ts = v => /^\d+(\.\d+)?$/.test(v) ? Math.round((Number(v) - 25569) * 864e5)
  : Date.parse((m => m ? `${m[1]}T${m[2].padStart(2, '0')}:${m[3]}${m[4] || ':00'}Z` : v)(String(v).match(/^(\d{4}-\d\d-\d\d) (\d{1,2}):(\d\d)(:\d\d)?$/)));
const COLS = ['received', 'lead_id', 'name', 'email', 'company', 'fit', 'service', 'budget_band', 'urgency', 'next_step',
  'summary', 'missing_info', 'red_flags', 'follow_up_subject', 'follow_up_body', 'tokens'];
const readRows = async () => {
  const r = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${env.LEADS_SHEET_ID}/values/${PLATFORM}!A2:P`,
    { headers: { Authorization: `Bearer ${token()}` } });
  const values = (await r.json()).values || [];
  const rows = {};
  for (const v of values) { const o = Object.fromEntries(COLS.map((k, i) => [k, v[i] ?? ''])); if (RESCORE ? o.lead_id : sent[o.lead_id] && ts(o.received) >= sent[o.lead_id] - 5000) rows[o.lead_id] = o; }
  return rows;
};
let rows = {};
const deadline = Date.now() + WAIT * 1000;
while (Date.now() < deadline || RESCORE) {
  rows = await readRows();
  process.stderr.write(`\r${Object.keys(rows).length}/${cases.length} rows`);
  if (RESCORE || Object.keys(rows).length >= cases.length) break;
  await new Promise(res => setTimeout(res, 15000));
}
process.stderr.write('\n');

// 3. Score
const PRICE = /\bR\s?\d[\d\s,]*(k\b)?|\bZAR\b|\$\s?\d/i;
const DATE = /\b(by|within|in)\s+\d+\s+(day|week|month)s?\b|\bnext week\b/i;
const res = cases.map(c => {
  const r = rows[c.lead.lead_id], e = c.expect;
  if (!r) return { id: c.lead.lead_id, missing: true, expect: e };
  return { id: c.lead.lead_id, expect: e, fit: r.fit, next_step: r.next_step, service: r.service,
    fit_ok: r.fit === e.fit, step_ok: r.next_step === e.next_step, service_ok: !e.service || r.service === e.service,
    alerted: ['call', 'email'].includes(r.next_step),
    quotes_price_or_date: PRICE.test(r.follow_up_body) || DATE.test(r.follow_up_body),
    latency_s: RESCORE ? null : (ts(r.received) - sent[c.lead.lead_id]) / 1000, tokens: r.tokens, summary: r.summary };
});
const ok = res.filter(r => !r.missing), pct = (n, d) => d ? `${(100 * n / d).toFixed(0)}% (${n}/${d})` : 'n/a';
const lat = ok.map(r => r.latency_s).filter(x => x !== null).sort((a, b) => a - b), q = p => lat.length ? lat[Math.min(lat.length - 1, Math.floor(p * lat.length))] : 'n/a';
const [inTok, outTok] = ok.reduce(([a, b], r) => { const [x, y] = (r.tokens || '0/0').split('/').map(Number); return [a + x, b + y]; }, [0, 0]);
const metrics = {
  platform: PLATFORM, leads: cases.length, rows_written: ok.length,
  fit_accuracy: pct(ok.filter(r => r.fit_ok).length, ok.length),
  next_step_accuracy: pct(ok.filter(r => r.step_ok).length, ok.length),
  high_fit_leads_caught: pct(ok.filter(r => r.expect.next_step === 'call' && r.next_step === 'call').length, ok.filter(r => r.expect.next_step === 'call').length),
  spam_or_decline_pinging_slack: ok.filter(r => r.expect.next_step === 'decline' && r.alerted).length,
  follow_ups_quoting_price_or_date: ok.filter(r => r.quotes_price_or_date).length,
  latency_s_p50: q(0.5), latency_s_p95: q(0.95),
  ai_cost_usd: +((inTok * 0.10 + outTok * 0.50) / 1e6).toFixed(5),   // Haiku 5.5: $0.10 in / $0.50 out per million tokens
};
const stamp = new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-');
mkdirSync(join(ROOT, 'eval/results'), { recursive: true });
const base = join(ROOT, `eval/results/${PLATFORM}-${stamp}${RESCORE ? '-rescore' : ''}`);
writeFileSync(`${base}.json`, JSON.stringify({ metrics, sent, results: res }, null, 2));
const misses = res.filter(r => r.missing || !r.fit_ok || !r.step_ok || r.quotes_price_or_date);
writeFileSync(`${base}.md`, [`# ${PLATFORM} (${stamp})`, '', '| Metric | Value |', '|---|---|',
  ...Object.entries(metrics).map(([k, v]) => `| ${k} | ${v} |`), '', `## Misses (${misses.length})`, '',
  ...misses.map(r => r.missing ? `- **${r.id}** no row written` :
    `- **${r.id}** fit ${r.fit} (expected ${r.expect.fit}), next step ${r.next_step} (expected ${r.expect.next_step})${r.quotes_price_or_date ? ', follow-up quotes a price or date' : ''}: ${r.summary}`)].join('\n') + '\n');
console.log(JSON.stringify(metrics, null, 2));
console.log(`report: ${base.replace(ROOT + '/', '')}.md`);

// The Zapier Code step must send exactly the request scripts/build_request.py defines and flatten the answer
// correctly. Runs the generated code with a fake fetch (no API calls): node eval/zapier.test.mjs
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const py = (...a) => execFileSync('python3', a, { cwd: ROOT }).toString();
const code = py('zapier/build_code.py');
const canon = v => Array.isArray(v) ? v.map(canon) : v && typeof v === 'object' ?
  Object.fromEntries(Object.keys(v).sort().map(k => [k, canon(v[k])])) : v;
const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor;

async function run(inputData, reply, status = 200) {
  let sent;
  const fetch = async (url, opts) => { sent = { url, headers: opts.headers, body: JSON.parse(opts.body) };
    return { ok: status === 200, status, json: async () => reply }; };
  const out = await new AsyncFunction('inputData', 'fetch', code)(inputData, fetch);
  return { sent, out };
}

let failed = 0;
const check = (name, ok) => { if (!ok) failed++; console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}`); };
const leads = readFileSync(join(ROOT, 'eval/leads.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l).lead);
const ai = { fit: 'high', service: 'support', budget_band: '50k_to_250k', urgency: 'high', next_step: 'call',
  summary: 'Crashing case system.', missing_info: ['hosting', 'users'], red_flags: [], follow_up_subject: 'S', follow_up_body: 'B' };
const reply = { content: [{ type: 'thinking', thinking: '' }, { type: 'text', text: JSON.stringify(ai) }], usage: { input_tokens: 1200, output_tokens: 300 } };

for (const lead of [leads[0], leads[16], { ...leads[5], message: 'Quotes "with" \\ odd ${chars}\nand lines' }]) {
  const { sent } = await run({ ...lead, api_key: 'test-key' }, reply);
  const want = JSON.parse(py('scripts/build_request.py', '--lead', JSON.stringify(lead)));
  check(`request identical to build_request.py (${lead.lead_id})`, JSON.stringify(canon(sent.body)) === JSON.stringify(canon(want)));
}
const { sent, out } = await run({ ...leads[18], api_key: 'test-key' }, reply);
check('key comes from the api_key input field', sent.headers['x-api-key'] === 'test-key');
check('text block found even after a thinking block', out.fit === 'high' && out.next_step === 'call');
check('lists flattened for the sheet', out.missing_info === 'hosting; users');
check('tokens recorded', out.tokens === '1200/300');
check('Slack text tagged [zapier]', out.slack_text.startsWith('[zapier]') && out.slack_text.includes('Naledi Mahlangu'));
const broken = (await run({ ...leads[0], api_key: 'k' }, { content: [{ type: 'text', text: 'oops' }] })).out;
check('unreadable output -> a row a person must check', broken.next_step === 'email' && broken.red_flags === 'AI output unreadable');
let threw = false;
try { await run({ ...leads[0], api_key: 'bad' }, { error: { message: 'invalid x-api-key' } }, 401); } catch (e) { threw = /401/.test(e.message); }
check('API errors fail the step loudly', threw);
const raw = (await run({ raw_body: JSON.stringify(leads[18]), api_key: 'k' }, reply)).out;
check('raw_body input parsed (Catch Raw Hook) and lead fields passed through', raw.lead_id === 't19' && raw.name === 'Naledi Mahlangu' && raw.company === 'Mahlangu Attorneys');

console.log(failed ? `\n${failed} failed` : '\nall passed');
process.exit(failed ? 1 : 0);

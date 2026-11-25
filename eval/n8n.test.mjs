// The n8n Code nodes must send exactly the request that scripts/build_request.py defines,
// so every platform is tested with the same prompt. No API calls: node eval/n8n.test.mjs
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const py = (...a) => execFileSync('python3', a, { cwd: ROOT }).toString();
const code = JSON.parse(py('scripts/build_n8n.py', '--code'));
const run = (js, input, named = {}) => new Function('$input', '$', js)(
  { first: () => ({ json: input }) }, n => ({ first: () => ({ json: named[n] }) }))[0].json;

// Same content, key order ignored (the API doesn't care about it)
const canon = v => Array.isArray(v) ? v.map(canon) : v && typeof v === 'object' ?
  Object.fromEntries(Object.keys(v).sort().map(k => [k, canon(v[k])])) : v;
let failed = 0;
const check = (name, ok) => { if (!ok) failed++; console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}`); };

const leads = readFileSync(join(ROOT, 'eval/leads.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l).lead);
for (const lead of [leads[0], leads[16], { ...leads[5], message: 'Quotes "with" \\ odd ${chars}\nand lines' }]) {
  const want = JSON.parse(py('scripts/build_request.py', '--lead', JSON.stringify(lead)));
  const got = run(code.build_js, { body: lead }).request;
  check(`request identical to build_request.py (${lead.lead_id})`, JSON.stringify(canon(got)) === JSON.stringify(canon(want)));
}

const ai = { fit: 'high', service: 'support', budget_band: '50k_to_250k', urgency: 'high', next_step: 'call',
  summary: 'Crashing case system, court deadlines.', missing_info: ['current hosting'], red_flags: [],
  follow_up_subject: 'Stabilising your case system', follow_up_body: 'Hi Naledi, ...' };
const parsed = run(code.parse_js, { content: [{ type: 'text', text: JSON.stringify(ai) }], usage: { input_tokens: 1200, output_tokens: 300 } },
  { 'Build request': { lead: leads[18] } });
check('row has the 16 contract columns', parsed.row.length === 16);
check('row carries the lead id and AI fields', parsed.row[1] === 't19' && parsed.row[5] === 'high' && parsed.row[9] === 'call');
check('tokens recorded', parsed.row[15] === '1200/300');
const broken = run(code.parse_js, { content: [{ type: 'text', text: 'not json' }] }, { 'Build request': { lead: leads[0] } });
check('unreadable AI output -> a row a person must check', broken.ai.next_step === 'email' && broken.ai.red_flags.includes('AI output unreadable'));
const slack = run(code.slack_js, {}, { 'Parse result': parsed });
check('Slack text names the lead and the step', slack.text.includes('Naledi Mahlangu') && slack.text.includes('high fit, call'));

console.log(failed ? `\n${failed} failed` : '\nall passed');
process.exit(failed ? 1 : 0);

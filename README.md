# One lead workflow, three platforms: n8n vs Make vs Zapier

The same AI lead-qualification workflow, built on **n8n**, **Make** and **Zapier** for a small software studio (11OCLOCK), then measured on the same 20 labelled test leads.

A website enquiry arrives by webhook. Claude (Haiku 5.5) qualifies it against the studio's services and rules and drafts a follow-up. Every lead is logged as a row in a Google Sheet, and the partners get a Slack alert only for leads worth a call or an email. Nothing is ever sent to the lead automatically.

**Results and the engineering differences found: [FINDINGS.md](FINDINGS.md).**

| | n8n | Make | Zapier |
|---|---|---|---|
| Fit accuracy (20 leads) | 90% | 90% | 95% |
| High-fit leads caught | 6/6 | 6/6 | 6/6 |
| Spam or declined leads sent to Slack | 0 | 0 | 0 |
| AI cost for 20 leads | $0.0089 | $0.0087 | $0.0088 |
| Runs on a free plan | Yes (self-hosted) | Yes (about 140 leads/month) | No (needs Pro) |

## How the comparison is kept fair

- **One contract** ([CONTRACT.md](CONTRACT.md)): the same webhook input, Claude request, Sheet columns and Slack rule on every platform.
- **One prompt, generated once.** [`scripts/build_request.py`](scripts/build_request.py) builds the Claude request from [`prompt/`](prompt/) and [`business/11oclock.md`](business/11oclock.md). Each platform's version is generated from it, and tests check that each one sends a byte-identical request:
  - n8n: [`scripts/build_n8n.py`](scripts/build_n8n.py) → [`n8n/lead-qualifier.json`](n8n/lead-qualifier.json)
  - Make: [`make/build_blueprint.py`](make/build_blueprint.py) → [`make/lead-qualifier.blueprint.json`](make/lead-qualifier.blueprint.json)
  - Zapier: [`zapier/build_code.py`](zapier/build_code.py) → [`zapier/code-step.js`](zapier/code-step.js) (the Code step; the other Zap steps are set up in Zapier's editor)
- **One benchmark.** [`eval/leads.jsonl`](eval/leads.jsonl) holds 20 leads labelled by the rules in [`eval/LABELING.md`](eval/LABELING.md): high fit, medium, low, spam, and one prompt-injection attempt. The prompt was not tuned on it.

## Running it

```bash
# Tests (no API calls)
node eval/n8n.test.mjs
node eval/zapier.test.mjs

# Benchmark one platform: sends the 20 leads to its webhook, then scores the rows it wrote to its Sheet tab
export GOOGLE_TOKEN_FILE=/path/to/token   # see scripts/google_token.py
node eval/run.mjs --platform n8n --url <webhook URL>
node eval/run.mjs --platform zapier --rescore   # score rows already in the Sheet, without sending
```

Secrets (Anthropic key, Slack webhook URL, Sheet ID) live in `.env` or in each platform's own credential fields, never in this repo.

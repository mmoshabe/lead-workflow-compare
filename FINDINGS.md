# Findings (n8n vs Make vs Zapier)

Same contract, same prompt and model (Claude Haiku 5.5), same 20 labelled leads ([eval/leads.jsonl](eval/leads.jsonl)).

| Metric | n8n (self-hosted) | Make (Free) | Zapier (Pro trial) |
|---|---|---|---|
| Rows written | 20/20 | 20/20 (first run 10/20, see below) | 20/20 |
| Fit accuracy | 90% | 90% | 95% |
| Next-step accuracy | 90% | 85% | 90% |
| High-fit leads caught | 6/6 | 6/6 | 6/6 |
| Spam/decline pinging Slack | 0 | 0 | 0 (11/11 call/email alerts arrived) |
| Follow-ups quoting a price or date | 0 | 0 | 0 |
| Latency p50 / p95 (lead sent → CRM row) | 3.2 s / 6.5 s | 3.4 s / 5.4 s | not measured (see below); the Code step alone took 4.9 s on the test lead |
| AI cost for 20 leads | $0.0089 | $0.0087 | $0.0088 |
| Platform cost | $0 (Oracle Always Free VM) | $0 on Free: about 7 credits per lead, so the 1,000 free credits cover about 140 leads a month | Needs Pro (from $19.99/month; ran on the 14-day trial): 3 tasks per alerted lead, 2 per filtered lead |

Accuracy differences of one lead are run-to-run model variance: Make missed t14 (student project → nurture instead of decline), which n8n got right with the identical prompt; Zapier also missed t14 but got t09 right, which both others missed. All three rated t08 (a sub-R20k CRM hookup) low/nurture against a medium/email label. Single runs of 20 can't separate platforms on accuracy. The differences that matter are below.

## Engineering differences found

1. **Parsing the AI response.** Claude's reply can start with a (hidden) thinking block, so the text answer isn't always the first content block. n8n's Code node finds the block by type and never noticed. Make's mapping `content[1].text` is positional, and broke on lead t07. Fix in Make: `first(map(3.data.content; text; type; text))`.
2. **One bad lead takes Make offline.** On that single error Make's default is to **deactivate the whole scenario** and hold the incoming leads in a queue. 10 of 20 leads waited until someone fixed and re-enabled it. In n8n, a failed run is just a failed run; the next lead still processes.
3. **Escaping user text into JSON.** Make builds HTTP bodies as text, so a lead containing a quote mark would break the request. It needs an extra "Transform to JSON" module (one more credit per lead). n8n's Code node builds the object natively.
4. **Setup.** Make imports a blueprint from a file (its "paste from clipboard" did nothing). Each webhook needs one sample request before fields can be mapped, and the HTTP module is now labelled "legacy". Secrets (Anthropic key, Slack URL) are pasted into module fields rather than stored as environment variables.
5. **Version control.** n8n's workflow is generated from code and lives in git. Make's blueprint can be exported and imported as JSON (we generate it from the same repo files), but connections and secrets have to be re-done by hand after import.
6. **Zapier can't run this on its free plan.** Webhooks, Code and multi-step Zaps are all Premium, and the free plan's 1-second Code limit fails the Claude call outright (it takes about 5 s). On Pro the Code step gets 30 s.
7. **Zapier mapping is by hand, field by field.** There is no import: every Sheet column is picked from a data picker (16 clicks-and-searches), and the Zap can't be regenerated from the repo. Only the Code step's JavaScript is generated and tested in git (`zapier/build_code.py`, `eval/zapier.test.mjs`). Using "Catch Raw Hook" and parsing the body in code avoided mapping all 10 lead fields into the Code step too.
8. **Zapier rewrites data on the way into Sheets.** The ISO timestamp `2026-11-25T06:40:16.330Z` arrived as `2026-11-25 6:40:16` (no zone, no milliseconds), and the first row as a date serial (`46351.27795`). Anything downstream that reads the Sheet has to cope; our harness initially discarded every Zapier row because of it. This is also why Zapier latency wasn't measured: the send times of that run were lost, and re-running for latency costs another ~$0.01.
9. **Filters are simpler in Zapier.** One "(Text) Is in: call,email" rule, versus Make's two OR conditions and n8n's IF node. Filtered runs show as "Filtered" in Zap history, which makes the spam check easy to audit.

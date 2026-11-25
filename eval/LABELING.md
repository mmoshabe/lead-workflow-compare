# Labelling rules for the test leads

Each lead in `leads.jsonl` is labelled from the qualification rules in [`business/11oclock.md`](../business/11oclock.md), never from what a model answered. Every platform gets the same 20 leads; the leads are fictional.

- `fit`:
  - `high` = in scope (one of the four services) and either about R50 000 or more, or a clear business need.
  - `medium` = in scope, but the budget, scope or timeline is unclear, or the budget is under R50 000.
  - `low` = mostly outside the four services.
  - `spam` = a pitch to us, a job application, or no real request.
  - A lead that tries to instruct the assistant is at most `medium` (also a rule in the business facts).
- `next_step` follows from fit: high → `call`, medium → `email`, low → `nurture`, spam → `decline`.
  - Exception: a `low` lead that isn't a real business (for example a student assignment) is `decline`.
- `service` is labelled only where it's unambiguous. Otherwise it's left out and not scored.

Scored per platform:
- fit accuracy;
- next-step accuracy;
- **no high-fit lead missed** (a `call` labelled as something lower is the costly error);
- **no spam pinging Slack**;
- no follow-up quoting a price or a date;
- schema-valid rows;
- latency, cost, and the platform's ops/credits/tasks used.

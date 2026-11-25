"""Generate the n8n version of the lead workflow (see CONTRACT.md).

    python3 scripts/build_n8n.py > /tmp/lead-qualifier.json              # for import: real Sheet ID from .env
    LEADS_SHEET_ID=YOUR_SHEET_ID python3 scripts/build_n8n.py > n8n/lead-qualifier.json   # the committed copy
    python3 scripts/build_n8n.py --code     # the Code-node bodies, for tests

Webhook -> Respond ok -> Build request -> Claude -> Parse result -> Log to Sheet -> Alert? -> Slack
"""

import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_request as br  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def dotenv() -> dict:
    p = ROOT / ".env"
    return dict(l.split("=", 1) for l in p.read_text().splitlines() if "=" in l and not l.startswith("#")) if p.exists() else {}


SHEET_ID = os.environ.get("LEADS_SHEET_ID") or dotenv().get("LEADS_SHEET_ID", "")
GOOGLE_CRED = {"oAuth2Api": {"id": os.environ.get("N8N_GOOGLE_CRED_ID", ""), "name": "Google"}}

# Mirrors build_request.user_message exactly (checked by eval/n8n.test.mjs).
BUILD_JS = r"""
const lead = $input.first().json.body || $input.first().json;
const FIELDS = __FIELDS__;
const lines = FIELDS.filter(f => f !== 'message').map(f => `${f}: ${lead[f] || '(not given)'}`);
const content = '<enquiry>\n' + lines.join('\n') + `\nmessage: ${lead.message || ''}\n</enquiry>`;
const request = { ...__TEMPLATE__, messages: [{ role: 'user', content }] };
return [{ json: { lead, request } }];
"""

PARSE_JS = r"""
// Flatten Claude's structured answer into one CRM row. Unreadable output becomes a row a person must check.
const r = $input.first().json;
const lead = $('Build request').first().json.lead;
let ai;
try { ai = JSON.parse((r.content || []).find(b => b.type === 'text').text); }
catch (e) { ai = { fit: 'medium', service: 'none', budget_band: 'unknown', urgency: 'normal', next_step: 'email',
                   summary: 'AI output unreadable: check this lead by hand', missing_info: [], red_flags: ['AI output unreadable'],
                   follow_up_subject: '', follow_up_body: '' }; }
const u = r.usage || {};
return [{ json: { lead, ai, row: [
  new Date().toISOString(), lead.lead_id || '', lead.name || '', lead.email || '', lead.company || '',
  ai.fit, ai.service, ai.budget_band, ai.urgency, ai.next_step, ai.summary,
  (ai.missing_info || []).join('; '), (ai.red_flags || []).join('; '), ai.follow_up_subject, ai.follow_up_body,
  `${u.input_tokens || 0}/${u.output_tokens || 0}` ] } }];
"""

SLACK_JS = r"""
const { lead, ai } = $('Parse result').first().json;
const bits = [lead.company, lead.budget, lead.timeline].filter(Boolean).join(', ');
return [{ json: { text: `[n8n] *New lead (${ai.fit} fit, ${ai.next_step})*: ${lead.name}${bits ? ', ' + bits : ''}.\n${ai.summary}\nDraft reply is in the leads sheet (row for ${lead.lead_id}).` } }];
"""


def code() -> dict:
    template = br.request({})
    template.pop("messages")
    build = BUILD_JS.replace("__FIELDS__", json.dumps(br.FIELDS)).replace("__TEMPLATE__", json.dumps(template))
    return {"build_js": build, "parse_js": PARSE_JS, "slack_js": SLACK_JS}


def node(name, type_, version, params, pos, **extra):
    return {"parameters": params, "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"11oclock-lead/{name}")), "name": name,
            "type": type_, "typeVersion": version, "position": pos, **extra}


def build() -> dict:
    c = code()
    nodes = [
        node("Lead webhook", "n8n-nodes-base.webhook", 2,
             {"httpMethod": "POST", "path": "11oclock-lead", "responseMode": "responseNode", "options": {}}, [0, 0],
             webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "11oclock-lead/webhook"))),
        node("Respond ok", "n8n-nodes-base.respondToWebhook", 1.1,
             {"respondWith": "json", "responseBody": '={"ok": true}', "options": {}}, [220, 0]),
        node("Build request", "n8n-nodes-base.code", 2, {"jsCode": c["build_js"]}, [440, 0]),
        node("Claude", "n8n-nodes-base.httpRequest", 4.2, {
            "method": "POST", "url": "https://api.anthropic.com/v1/messages",
            "sendHeaders": True, "headerParameters": {"parameters": [
                {"name": "x-api-key", "value": "={{ $env.ANTHROPIC_API_KEY }}"},
                {"name": "anthropic-version", "value": "2026-10-21"},
                {"name": "content-type", "value": "application/json"}]},
            "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.request) }}",
            "options": {"timeout": 60000}}, [660, 0], retryOnFail=True, maxTries=3, waitBetweenTries=3000),
        node("Parse result", "n8n-nodes-base.code", 2, {"jsCode": c["parse_js"]}, [880, 0]),
        node("Log to Sheet", "n8n-nodes-base.httpRequest", 4.2, {
            "method": "POST",
            "url": f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/n8n!A1:P1:append"
                   "?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
            "authentication": "genericCredentialType", "genericAuthType": "oAuth2Api",
            "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify({ values: [$json.row] }) }}",
            "options": {}}, [1100, 0], credentials=GOOGLE_CRED, retryOnFail=True, maxTries=3, waitBetweenTries=3000),
        node("Alert?", "n8n-nodes-base.if", 2.2, {"conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
            "conditions": [
                {"id": "step", "leftValue": "={{ ['call', 'email'].includes($('Parse result').first().json.ai.next_step) }}",
                 "rightValue": "", "operator": {"type": "boolean", "operation": "true", "singleValue": True}},
                {"id": "slack-on", "leftValue": "={{ $env.SLACK_LEADS_WEBHOOK_URL }}", "rightValue": "",
                 "operator": {"type": "string", "operation": "notEmpty", "singleValue": True}}],
            "combinator": "and"}, "options": {}}, [1320, 0]),
        node("Slack message", "n8n-nodes-base.code", 2, {"jsCode": c["slack_js"]}, [1540, -100]),
        node("Slack", "n8n-nodes-base.httpRequest", 4.2, {
            "method": "POST", "url": "={{ $env.SLACK_LEADS_WEBHOOK_URL }}",
            "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify({ text: $json.text }) }}",
            "options": {}}, [1760, -100], retryOnFail=True, maxTries=2, waitBetweenTries=3000),
    ]
    to = lambda *n: [[{"node": x, "type": "main", "index": 0}] for x in n]
    connections = {
        "Lead webhook": {"main": to("Respond ok")}, "Respond ok": {"main": to("Build request")},
        "Build request": {"main": to("Claude")}, "Claude": {"main": to("Parse result")},
        "Parse result": {"main": to("Log to Sheet")}, "Log to Sheet": {"main": to("Alert?")},
        "Alert?": {"main": [[{"node": "Slack message", "type": "main", "index": 0}], []]},
        "Slack message": {"main": to("Slack")},
    }
    return {"id": "elevenOclockLeads", "name": "11OCLOCK lead qualifier", "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "all"}, "active": False, "pinData": {}, "tags": []}


if __name__ == "__main__":
    json.dump(code() if "--code" in sys.argv else build(), sys.stdout, indent=2, ensure_ascii=False)

"""Generate the Make scenario blueprint for the lead workflow (see CONTRACT.md).

    python3 make/build_blueprint.py > make/lead-qualifier.blueprint.json

Import it in Make (scenario editor -> ... -> Import Blueprint), then in Make's own screens:
  - module 1: create the webhook ("11oclock-lead") and copy its URL,
  - module 3: replace PASTE_ANTHROPIC_API_KEY with your key,
  - module 5: connect Google and pick the "make" tab (columns are pre-mapped),
  - module 7: replace PASTE_SLACK_WEBHOOK_URL with the #11oclock-leads webhook URL.
Secrets are never written into this file.

Modules: Webhook -> Transform to JSON (escape the lead text) -> HTTP Claude -> Parse JSON
         -> Google Sheets add row -> [filter: call/email] Transform to JSON (Slack text) -> HTTP Slack
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_request as br  # noqa: E402


def lead_text() -> str:
    """Same text as build_request.user_message, written as a Make mapping."""
    lines = [f"{f}: {{{{ifempty(1.{f}; \"(not given)\")}}}}" for f in br.FIELDS if f != "message"]
    return "<enquiry>\n" + "\n".join(lines) + "\nmessage: {{1.message}}\n</enquiry>"


def claude_body() -> str:
    """Raw JSON body: static parts pre-serialised here, the lead text inserted already JSON-escaped by module 2."""
    template = br.request({})
    template.pop("messages")
    head = json.dumps(template, ensure_ascii=False)[:-1]  # drop the closing brace
    return head + ', "messages": [{"role": "user", "content": {{2.json}}}]}'


def mod(id_, module, version, mapper, x, parameters=None, **extra):
    return {"id": id_, "module": module, "version": version, "parameters": parameters or {}, "mapper": mapper,
            "metadata": {"designer": {"x": x, "y": 0}}, **extra}


ROW = ["{{now}}", "{{1.lead_id}}", "{{1.name}}", "{{1.email}}", "{{1.company}}", "{{4.fit}}", "{{4.service}}",
       "{{4.budget_band}}", "{{4.urgency}}", "{{4.next_step}}", "{{4.summary}}", "{{join(4.missing_info; \"; \")}}",
       "{{join(4.red_flags; \"; \")}}", "{{4.follow_up_subject}}", "{{4.follow_up_body}}",
       "{{3.data.usage.input_tokens}}/{{3.data.usage.output_tokens}}"]

SLACK_TEXT = ("[make] *New lead ({{4.fit}} fit, {{4.next_step}})*: {{1.name}}, {{1.company}}, {{1.budget}}, {{1.timeline}}.\n"
              "{{4.summary}}\nDraft reply is in the leads sheet (row for {{1.lead_id}}).")


def blueprint() -> dict:
    flow = [
        mod(1, "gateway:CustomWebHook", 1, {}, 0, {"maxResults": 1}),
        mod(2, "json:TransformToJSON", 1, {"object": lead_text()}, 300),
        mod(3, "http:ActionSendData", 3, {
            "url": "https://api.anthropic.com/v1/messages", "method": "post",
            "headers": [{"name": "x-api-key", "value": "PASTE_ANTHROPIC_API_KEY"},
                        {"name": "anthropic-version", "value": "2026-10-21"},
                        {"name": "content-type", "value": "application/json"}],
            "qs": [], "bodyType": "raw", "contentType": "application/json", "data": claude_body(),
            "parseResponse": True, "timeout": "60", "shareCookies": False, "rejectUnauthorized": True,
            "followRedirect": True, "useMtls": False, "gzip": True, "useQuerystring": False, "followAllRedirects": False,
            "serializeUrl": False, "ca": "", "authUser": "", "authPass": ""}, 600, {"handleErrors": True, "useNewZLibDeCompress": True}),
        # Pick the text block by type: the response can start with a (hidden) thinking block, so position 1 is not reliable.
        mod(4, "json:ParseJSON", 1, {"json": "{{first(map(3.data.content; \"text\"; \"type\"; \"text\"))}}"}, 900),
        mod(5, "google-sheets:addRow", 2, {
            "mode": "select", "valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS", "from": "drive",
            "sheetId": "make", "includesHeaders": True, "insertUnformatted": False,
            "values": {str(i): v for i, v in enumerate(ROW)}}, 1200),
        mod(6, "json:TransformToJSON", 1, {"object": SLACK_TEXT}, 1500,
            filter={"name": "Only call or email", "conditions": [
                [{"a": "{{4.next_step}}", "o": "text:equal", "b": "call"}],
                [{"a": "{{4.next_step}}", "o": "text:equal", "b": "email"}]]}),
        mod(7, "http:ActionSendData", 3, {
            "url": "PASTE_SLACK_WEBHOOK_URL", "method": "post", "headers": [], "qs": [],
            "bodyType": "raw", "contentType": "application/json", "data": "{\"text\": {{6.json}}}",
            "parseResponse": False, "timeout": "", "shareCookies": False, "rejectUnauthorized": True,
            "followRedirect": True, "useMtls": False, "gzip": True, "useQuerystring": False, "followAllRedirects": False,
            "serializeUrl": False, "ca": "", "authUser": "", "authPass": ""}, 1800, {"handleErrors": True, "useNewZLibDeCompress": True}),
    ]
    return {"name": "11OCLOCK lead qualifier (Make)", "flow": flow,
            "metadata": {"instant": True, "version": 1,
                         "scenario": {"roundtrips": 1, "maxErrors": 3, "autoCommit": True, "autoCommitTriggerLast": True,
                                      "sequential": False, "confidential": False, "dataloss": False, "dlq": False,
                                      "freshVariables": False},
                         "designer": {"orphans": []}}}


if __name__ == "__main__":
    json.dump(blueprint(), sys.stdout, indent=2, ensure_ascii=False)

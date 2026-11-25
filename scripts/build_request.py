"""Build the one Claude request every platform sends, so prompt and model are identical.

    python3 scripts/build_request.py            -> prompt/request.template.json (placeholders like {{name}})
    python3 scripts/build_request.py --lead '{"name": ...}'   -> a filled request body (used by the n8n builder and eval)

Platforms map lead fields into the placeholders in the user message. The system prompt and schema are fixed.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = "claude-haiku-5-5"
FIELDS = ["name", "email", "company", "phone", "project_type", "budget", "timeline", "source", "message"]


def system_prompt() -> str:
    return ((ROOT / "prompt/qualify.md").read_text().strip() + "\n\n<business_facts>\n"
            + (ROOT / "business/11oclock.md").read_text().strip() + "\n</business_facts>")


def user_message(lead: dict) -> str:
    lines = [f"{f}: {lead.get(f, '') or '(not given)'}" for f in FIELDS if f != "message"]
    return "<enquiry>\n" + "\n".join(lines) + f"\nmessage: {lead.get('message', '')}\n</enquiry>"


def request(lead: dict) -> dict:
    return {
        "model": MODEL,
        "max_tokens": 1500,
        "system": system_prompt(),
        "messages": [{"role": "user", "content": user_message(lead)}],
        "output_config": {"effort": "low", "format": {"type": "json_schema",
                                                     "schema": json.loads((ROOT / "prompt/schema.json").read_text())}},
    }


if __name__ == "__main__":
    if "--lead" in sys.argv:
        json.dump(request(json.loads(sys.argv[sys.argv.index("--lead") + 1])), sys.stdout, ensure_ascii=False)
    else:
        template = request({f: "{{" + f + "}}" for f in FIELDS})
        out = ROOT / "prompt/request.template.json"
        out.write_text(json.dumps(template, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {out.relative_to(ROOT)} ({len(template['system'])} chars of system prompt)")

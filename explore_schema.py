"""
Explore PBS Wisconsin Airtable base for presentation.
Shows base structure (schema) and sample data so you can demonstrate
what the Airtable API returns and how it will power the RAG chatbot.
"""

import os
import re
import urllib.parse
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.airtable.com/v0"
META_URL = "https://api.airtable.com/v0/meta/bases/{base_id}/tables"
MAX_SAMPLE_RECORDS = 3
MAX_FIELDS_PER_RECORD = 10
MAX_FIELD_VALUE_LEN = 100
FIELD_NAME_WIDTH = 40
SCHEMA_FIELDS_SHOWN = 15


def format_value(v):
    """Turn a field value into a short, readable string for display."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, dict):
        if "url" in v:
            return v.get("filename", v.get("url", ""))[:MAX_FIELD_VALUE_LEN]
        return str(v)[:MAX_FIELD_VALUE_LEN]
    if isinstance(v, list):
        if not v:
            return ""
        parts = []
        for item in v[:4]:
            if isinstance(item, dict):
                parts.append(item.get("name", item.get("filename", str(item)[:25])))
            else:
                parts.append(str(item))
        s = ", ".join(parts)
        if len(v) > 4:
            s += f" (+{len(v) - 4} more)"
        return s[:MAX_FIELD_VALUE_LEN] + ("..." if len(s) > MAX_FIELD_VALUE_LEN else "")
    s = str(v).strip()
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s)
    if len(s) > MAX_FIELD_VALUE_LEN:
        s = s[:MAX_FIELD_VALUE_LEN].rsplit(" ", 1)[0] + "..."
    return s


def main():
    api_key = os.getenv("AIRTABLE_API_KEY")
    base_id = os.getenv("AIRTABLE_BASE_ID")
    if not api_key:
        print("Error: AIRTABLE_API_KEY missing in .env")
        return
    if not base_id:
        print("Error: AIRTABLE_BASE_ID missing in .env")
        return

    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        r = requests.get(META_URL.format(base_id=base_id), headers=headers, timeout=30)
        r.raise_for_status()
        schema = r.json()
    except requests.exceptions.RequestException as e:
        err = getattr(e, "response", None)
        if err is not None and err.text:
            print("API error:", err.text[:500])
        else:
            print("Request failed:", e)
        return

    tables = schema.get("tables", [])

    # -------------------------------------------------------------------------
    # PRESENTATION: Title & overview
    # -------------------------------------------------------------------------
    print()
    print("  " + "=" * 66)
    print("  PBS WISCONSIN — AIRTABLE BASE DEMO")
    print("  " + "=" * 66)
    print()
    print("  What we're showing:")
    print("    • This base is used for project management, tasks, video promotions,")
    print("      contacts, staff, and more. We connect to it via the Airtable API.")
    print()
    print(f"  Base ID:  {base_id}")
    print(f"  Tables:   {len(tables)}")
    print()

    # -------------------------------------------------------------------------
    # 1. BASE STRUCTURE (Metadata API)
    # -------------------------------------------------------------------------
    print("  " + "-" * 66)
    print("  1. BASE STRUCTURE  (Metadata API — tables and fields)")
    print("  " + "-" * 66)
    print()
    for t in tables:
        name = t.get("name", "?")
        tid = t.get("id", "?")
        fields = t.get("fields", [])
        print(f"  Table: {name}")
        print(f"    ID: {tid}  ·  {len(fields)} fields")
        for f in fields[:SCHEMA_FIELDS_SHOWN]:
            fname = (f.get("name", "?") or "?")[:36]
            ftype = f.get("type", "?")
            print(f"      • {fname:<36}  {ftype}")
        if len(fields) > SCHEMA_FIELDS_SHOWN:
            print(f"      ... and {len(fields) - SCHEMA_FIELDS_SHOWN} more fields")
        print()

    # -------------------------------------------------------------------------
    # 2. SAMPLE DATA (Records API)
    # -------------------------------------------------------------------------
    print("  " + "-" * 66)
    print(f"  2. SAMPLE DATA  (Records API — up to {MAX_SAMPLE_RECORDS} records per table)")
    print("  " + "-" * 66)
    print()

    for t in tables:
        name = t.get("name", "?")
        tid = t.get("id", "?")
        url = f"{BASE_URL}/{base_id}/{urllib.parse.quote(tid)}"
        try:
            r = requests.get(
                url,
                headers=headers,
                params={"pageSize": MAX_SAMPLE_RECORDS},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except requests.exceptions.RequestException as e:
            print(f"  {name}: Error — {e}\n")
            continue

        records = data.get("records", [])
        print(f"  Table: {name}")
        if not records:
            print("    (no records)")
            print()
            continue
        for i, rec in enumerate(records):
            rec_id = rec.get("id", "?")
            fields = rec.get("fields", {})
            print(f"    Record {i + 1}  (id: {rec_id})")
            shown = 0
            for k, v in fields.items():
                if shown >= MAX_FIELDS_PER_RECORD:
                    print(f"    {'...':<{FIELD_NAME_WIDTH}}  (+{len(fields) - MAX_FIELDS_PER_RECORD} more fields)")
                    break
                display = format_value(v)
                if display == "":
                    continue
                label = (k[: FIELD_NAME_WIDTH - 2] + "..") if len(k) > FIELD_NAME_WIDTH else k
                val_lines = [display[j : j + 64] for j in range(0, len(display), 64)]
                print(f"    {label:<{FIELD_NAME_WIDTH}}  {val_lines[0]}")
                for extra in val_lines[1:]:
                    print(f"    {'':<{FIELD_NAME_WIDTH}}  {extra}")
                shown += 1
            print()
        print()

    # -------------------------------------------------------------------------
    # Summary for the audience
    # -------------------------------------------------------------------------
    print("  " + "=" * 66)
    print("  SUMMARY — What this demonstrates")
    print("  " + "=" * 66)
    print()
    print("  • Schema (tables, fields, types) is available via the Metadata API.")
    print("  • Records (real project names, statuses, dates, etc.) come from the")
    print("    Records API. We can query by table and page through results.")
    print("  • This data can be indexed and used by the Slack RAG chatbot to answer")
    print("    questions about PBS Wisconsin projects, promotions, and tasks.")
    print()


if __name__ == "__main__":
    main()

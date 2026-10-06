#!/usr/bin/env bash
# Push the generated demo data through the real ingest endpoints, and sync defects
# from the mock JIRA through the real sync job. Run `python scripts/generate_demo_data.py` first.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="${QA_API_BASE_URL:-http://127.0.0.1:8001}"
DATA="$REPO_ROOT/samples/generated"

if [[ ! -f "$DATA/manifest.json" ]]; then
  echo "ERROR: no generated data. Run: python scripts/generate_demo_data.py" >&2
  exit 1
fi

TOKEN="${QA_INGEST_TOKEN:-}"
if [[ -z "$TOKEN" && -f "$REPO_ROOT/.env" ]]; then
  TOKEN="$(grep -E '^QA_INGEST_TOKEN=' "$REPO_ROOT/.env" | tail -n 1 | cut -d= -f2- || true)"
fi
if [[ -z "$TOKEN" ]]; then
  echo "ERROR: no ingest token. Run: make setup   (or set QA_INGEST_TOKEN)" >&2
  exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
# The token goes in a header file so it never shows up in the process list.
printf 'Authorization: Bearer %s\n' "$TOKEN" > "$WORK/auth-header"

echo "Pushing Playwright reports to $API ..."
python3 - "$API" "$DATA" "$WORK/auth-header" <<'PY'
import json, subprocess, sys
api, data_dir, header_file = sys.argv[1], sys.argv[2], sys.argv[3]
manifest = json.load(open(f"{data_dir}/manifest.json"))
for index, entry in enumerate(manifest["playwright"], 1):
    args = [
        "curl", "-fsS", "-X", "POST", f"{api}/api/v1/ingest/playwright",
        "-H", f"@{header_file}",
        "-F", f"report=@{data_dir}/{entry['file']};type=application/json",
    ]
    for key in ("application_code", "region", "environment", "product_type", "job_name", "build_number"):
        args += ["-F", f"{key}={entry[key]}"]
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)
    if index % 20 == 0 or index == len(manifest["playwright"]):
        print(f"  {index}/{len(manifest['playwright'])} reports")
PY

echo "Syncing defects from the mock JIRA ..."
(cd "$REPO_ROOT/apps/api" && uv run python ../../scripts/sync_jira.py --mock --dashboard "$API")

echo "Importing agent run logs ..."
curl -fsS -X POST "$API/api/v1/ingest/agent-runs" \
  -H "@$WORK/auth-header" \
  -F "logs=@$DATA/agent-runs.json;type=application/json" | python3 -m json.tool

echo "Done."

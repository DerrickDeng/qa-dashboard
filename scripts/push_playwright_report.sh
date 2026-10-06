#!/usr/bin/env bash
# Push a Playwright HTML report folder to the dashboard. Stands in for the CI
# step while tests run on a laptop.
#
#   scripts/push_playwright_report.sh [report-dir] [options]
#
#   report-dir     the playwright-html folder
#                  default: $PLAYWRIGHT_REPORT_DIR, else ../playwright-UI-auto-v2/reports/playwright-html
#   --app CODE     application code, e.g. QAD   (default: $QA_APPLICATION_CODE)
#   --region hk    only needed when the project name is not region-env
#   --env sit      only needed when the project name is not region-env
#   --product X    product type
#   --build N      a build label (default: local-<timestamp>)
#   --no-bundle    send only index.html; "View report" falls back to the JSON view
#
# The ingest token comes from $QA_INGEST_TOKEN, else from .env (make setup creates it).
# No Playwright config change is needed: index.html already embeds the report.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="${QA_API_BASE_URL:-http://127.0.0.1:8001}"
WEB="${QA_WEB_BASE_URL:-http://127.0.0.1:5174}"

REPORT_DIR="${PLAYWRIGHT_REPORT_DIR:-$REPO_ROOT/../playwright-UI-auto-v2/reports/playwright-html}"
APP="${QA_APPLICATION_CODE:-}"
REGION=""
ENVIRONMENT=""
PRODUCT=""
BUILD="local-$(date +%Y%m%d-%H%M%S)"
WITH_BUNDLE=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app) APP="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --env) ENVIRONMENT="$2"; shift 2 ;;
    --product) PRODUCT="$2"; shift 2 ;;
    --build) BUILD="$2"; shift 2 ;;
    --no-bundle) WITH_BUNDLE=0; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    -*) echo "Unknown option: $1" >&2; exit 2 ;;
    *) REPORT_DIR="$1"; shift ;;
  esac
done

if [[ ! -f "$REPORT_DIR/index.html" ]]; then
  echo "ERROR: no index.html in $REPORT_DIR" >&2
  echo "Run the tests first, or pass the playwright-html folder as the first argument." >&2
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

if ! curl -fsS "$API/health" >/dev/null 2>&1; then
  echo "ERROR: the dashboard API is not reachable at $API. Start it with: make up" >&2
  exit 1
fi

REPORT_DIR="$(cd "$REPORT_DIR" && pwd)"

# Record which commit of the test repo produced the report, when there is one.
COMMIT="$(git -C "$REPORT_DIR" rev-parse HEAD 2>/dev/null || true)"
BRANCH="$(git -C "$REPORT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
# The token goes in a header file so it never shows up in the process list.
printf 'Authorization: Bearer %s\n' "$TOKEN" > "$WORK/auth-header"

args=(
  -sS -X POST "$API/api/v1/ingest/playwright"
  -H "@$WORK/auth-header"
  -F "report=@$REPORT_DIR/index.html;type=text/html"
  -F "application_code=$APP"
  -F "region=$REGION"
  -F "environment=$ENVIRONMENT"
  -F "product_type=$PRODUCT"
  -F "job_name=local"
  -F "build_number=$BUILD"
  -F "branch=$BRANCH"
  -F "commit_sha=$COMMIT"
)

if [[ "$WITH_BUNDLE" == 1 ]]; then
  (cd "$(dirname "$REPORT_DIR")" && zip -qr "$WORK/playwright-html.zip" "$(basename "$REPORT_DIR")")
  echo "Bundle: $(du -h "$WORK/playwright-html.zip" | cut -f1)"
  args+=(-F "bundle=@$WORK/playwright-html.zip;type=application/zip")
fi

echo "Pushing $REPORT_DIR ..."
RESPONSE="$(curl "${args[@]}" -w $'\n%{http_code}')"
STATUS="${RESPONSE##*$'\n'}"
BODY="${RESPONSE%$'\n'*}"
if [[ "$STATUS" != 200 ]]; then
  echo "ERROR: the dashboard answered $STATUS: $BODY" >&2
  exit 1
fi
echo "$BODY" | python3 -m json.tool
echo "Dashboard: $WEB"

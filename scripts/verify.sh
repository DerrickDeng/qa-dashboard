#!/usr/bin/env bash
# Format, lint, types, tests, and the frontend build. Non-zero on the first failure.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

step() { printf '\n=== %s ===\n' "$1"; }

step "Backend format"
(cd apps/api && uv run ruff format --check . ../mock-jira --config pyproject.toml)

step "Backend lint"
(cd apps/api && uv run ruff check . ../mock-jira --config pyproject.toml)

step "Backend types"
(cd apps/api && uv run mypy)

step "Backend tests"
(cd apps/api && uv run pytest -q -p no:warnings)

step "Frontend lint"
(cd apps/web && npm run lint --silent)

step "Frontend types and production build"
(cd apps/web && npm run build --silent)

printf '\nAll verification steps passed.\n'

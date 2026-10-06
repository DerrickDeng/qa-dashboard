SHELL := /bin/bash
API ?= http://127.0.0.1:8001

.DEFAULT_GOAL := help
.PHONY: help setup up down demo push-report sync-jira \
	user-add user-list user-reset-password user-disable user-enable \
	test verify clean

help: ## Show the available commands
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-20s %s\n", $$1, $$2}'

setup: ## Install dependencies and create .env with generated secrets
	cd apps/api && uv sync --all-groups
	cd apps/web && npm install
	@python3 scripts/ensure_env.py

up: ## Start the API :8001, the dashboard :5174, and the mock JIRA :8002
	@python3 scripts/ensure_env.py
	@./scripts/run-local.sh start

down: ## Stop all three
	@./scripts/run-local.sh stop

demo: ## Generate demo data and push it through the real ingest endpoints
	python3 scripts/generate_demo_data.py
	@QA_API_BASE_URL="$(API)" ./scripts/push_demo_data.sh

push-report: ## Push a Playwright HTML report (REPORT=dir APP=code, both optional)
	@./scripts/push_playwright_report.sh $(if $(REPORT),"$(REPORT)") $(if $(APP),--app "$(APP)")

sync-jira: ## Sync defects from the mock JIRA into the dashboard
	cd apps/api && uv run python ../../scripts/sync_jira.py --mock --dashboard "$(API)"

# Accounts take NAME=, not USER=: the shell already sets USER to your login name.
user-add: ## Create an account (NAME=name; prompts for the password)
	@test -n "$(NAME)" || { echo "Usage: make user-add NAME=<name>" >&2; exit 2; }
	@cd apps/api && uv run python ../../scripts/manage_users.py add "$(NAME)"

user-list: ## List accounts
	@cd apps/api && uv run python ../../scripts/manage_users.py list

user-reset-password: ## Set a new password (NAME=name); ends that account's sessions
	@test -n "$(NAME)" || { echo "Usage: make user-reset-password NAME=<name>" >&2; exit 2; }
	@cd apps/api && uv run python ../../scripts/manage_users.py reset-password "$(NAME)"

user-disable: ## Disable an account (NAME=name) and end its sessions
	@test -n "$(NAME)" || { echo "Usage: make user-disable NAME=<name>" >&2; exit 2; }
	@cd apps/api && uv run python ../../scripts/manage_users.py disable "$(NAME)"

user-enable: ## Re-enable an account (NAME=name)
	@test -n "$(NAME)" || { echo "Usage: make user-enable NAME=<name>" >&2; exit 2; }
	@cd apps/api && uv run python ../../scripts/manage_users.py enable "$(NAME)"

test: ## Backend tests
	cd apps/api && uv run pytest -q -p no:warnings

verify: ## Format, lint, types, tests, frontend build
	@./scripts/verify.sh

clean: ## Remove the database (accounts included), uploaded reports, and demo data
	rm -rf qa_dashboard.db apps/api/qa_dashboard.db storage samples/generated .runtime
	@echo "Cleaned."

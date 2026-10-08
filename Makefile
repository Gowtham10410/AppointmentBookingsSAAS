.PHONY: db-up db-down backend-install backend-run backend-test frontend-install frontend-dev frontend-test lint format seed e2e

DB_SERVICE := mysql

help:
	@echo "Available targets: db-up, db-down, backend-install, backend-run, backend-test, frontend-install, frontend-dev, frontend-test, lint, format, seed, e2e"

db-up:
	docker compose up -d $(DB_SERVICE)

db-down:
	docker compose down

backend-install:
	@echo "Backend dependency install is not available yet in this bootstrap stage."

backend-run:
	@echo "Backend app startup is not available yet in this bootstrap stage."

backend-test:
	@echo "Backend tests are not available yet in this bootstrap stage."

frontend-install:
	@echo "Frontend dependency install is not available yet in this bootstrap stage."

frontend-dev:
	@echo "Frontend dev server is not available yet in this bootstrap stage."

frontend-test:
	@echo "Frontend tests are not available yet in this bootstrap stage."

lint:
	@echo "Project linting is not available yet in this bootstrap stage."

format:
	@echo "Formatting is not available yet in this bootstrap stage."

seed:
	@echo "Seed command is not available yet in this bootstrap stage."

e2e:
	@echo "E2E suite is not available yet in this bootstrap stage."

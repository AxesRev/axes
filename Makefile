.PHONY: help install dev-install setup-hooks format lint type-check security test test-api test-cov clean run ci-check

help:
	@echo "Available commands:"
	@echo "  make install       - Install production dependencies"
	@echo "  make dev-install   - Install all dependencies + git hooks"
	@echo "  make setup-hooks   - Reinstall git hooks (if needed)"
	@echo "  make format        - Format code with ruff"
	@echo "  make lint          - Lint code with ruff"
	@echo "  make type-check    - Run ty type checking"
	@echo "  make security      - Run security checks with bandit"
	@echo "  make test          - Run all tests"
	@echo "  make test-api      - Run aegra-api tests only"
	@echo "  make test-cov      - Run tests with coverage"
	@echo "  make ci-check      - Run all CI checks locally"
	@echo "  make clean         - Clean cache files"
	@echo "  make run           - Run the server"

SERVICES := langraph_server graph_service billing_service tenant_service integrations_service slack_app neo4j_mcp

install:
	for s in $(SERVICES); do uv sync --project $$s --no-dev || exit 1; done

dev-install:
	uv sync
	for s in $(SERVICES); do uv sync --project $$s || exit 1; done
	@uv run pre-commit install
	@uv run pre-commit install --hook-type commit-msg
	@echo ""
	@echo "Done! Dependencies installed and git hooks set up."

setup-hooks:
	uv run pre-commit install
	@uv run pre-commit install --hook-type commit-msg
	@echo ""
	@echo "Git hooks reinstalled!"

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .

type-check:
	uv run --project langraph_server ty check langraph_server/src/

security:
	uv run --project langraph_server bandit -c pyproject.toml -r langraph_server/src/

test: test-api

test-api:
	uv run --project langraph_server pytest langraph_server/tests/

test-cov:
	uv run --project langraph_server pytest langraph_server/tests/ --cov=langraph_server/src --cov-report=html --cov-report=term

ci-check: format lint
	-uv run --project langraph_server ty check langraph_server/src/
	-uv run --project langraph_server bandit -c pyproject.toml -r langraph_server/src/
	$(MAKE) test
	@echo ""
	@echo "All CI checks completed! (ty and bandit are non-blocking)"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ty_cache .ruff_cache htmlcov 2>/dev/null || true

run:
	AEGRA_CONFIG=langraph_server/aegra.json PYTHONPATH=langraph_server uv run --project langraph_server uvicorn aegra_api.main:app --reload --loop asyncio

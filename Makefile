.PHONY: setup-dev test test-full test-postgres lint

# Install all Python runtime and development dependencies.
# Run this once after cloning or when requirements change.
setup-dev:
	pip install -r AINDY/requirements.txt
	pip install fakeredis prometheus-client
	@echo "Dev dependencies installed. Run 'make test' to verify."

# Default test suite (SQLite, fast, no external services required).
test:
	pytest tests/ -x -q \
	  --ignore=tests/unit/test_redis_queue_retry.py \
	  --ignore=tests/unit/test_resource_manager_redis.py

# Full test suite (all files including redis and prometheus tests).
# Requires: pip install redis==5.0.4 fakeredis prometheus-client
# Or run: make setup-dev
test-full:
	pytest tests/ -x -q

# PostgreSQL test suite (requires postgres on localhost:5433).
# See docs/ops/RUNBOOK.md for setup.
test-postgres:
	pytest tests/ -q -c pytest.postgres.ini

# Lint
lint:
	ruff check .

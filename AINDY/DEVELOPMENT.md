# Development Guide

This document describes how to set up a local development environment, run the system, and execute tests.

It is intended for developers working on the project locally.

---

# Local Setup

## 1. Clone the Repository

```
git clone <repository-url>
cd masterplan-infiniteweave-monday-node-2025-0411
```

---

## 2. Python Environment

Create a virtual environment:

```
python -m venv .venv
```

Activate the environment.

### Windows (PowerShell)

```
.venv\Scripts\Activate
```

### macOS / Linux

```
source .venv/bin/activate
```

---

## 3. Install Dependencies

Install required packages:

```
pip install -r requirements.txt
```

If a requirements file is not present, install dependencies used by the project manually.

---

# Environment Configuration

The project relies on a properly configured runtime environment.

Validate your environment configuration using:

```
python verify_env_config.py
```

This script checks that required environment variables and configuration values are available.

If the script reports errors, correct the configuration before running services.

---

# Running the System

The repository includes scripts to start and stop system services.

## Start All Services

PowerShell:

```
./start_all.ps1
```

This script launches the backend services required for local operation.

---

## Stop All Services

PowerShell:

```
./stop_all.ps1
```

Stops all services started by the development environment.

---

# Running Tests

Tests are located in the `tests/` directory.

Run the test suite using:

```
pytest
```

Example tests in the repository include:

```
test_calculations.py
test_import.py
test_routes.py
```

Tests should pass before submitting any pull request.

---

# Development Workflow

Typical development process:

1. Pull the latest changes
2. Create a feature branch
3. Implement changes
4. Run tests
5. Update documentation if necessary
6. Submit a pull request

Example:

```
git checkout -b feature/new-module
```

---

# Code Organization

Key project directories:

```
AINDY/          Core system implementation
client/         Client interface components
generated_code/ Generated artifacts
docs/           System documentation
tests/          Test suite
```

Documentation describing the system architecture is located in:

```
docs/architecture/
```

Interface specifications are located in:

```
docs/interfaces/
```

---

# Debugging

When debugging issues:

1. Check service logs
2. Verify environment configuration
3. Run tests for the affected components

Most system behavior is described in the architecture documentation.

Relevant documents include:

```
docs/architecture/SYSTEM_SPEC.md
docs/governance/INVARIANTS.md
docs/interfaces/API_CONTRACTS.md
```

---

# Updating Documentation

Architecture and interface changes must be reflected in the documentation.

Update relevant files in:

```
docs/
```

Examples:

* architecture changes → `docs/architecture/`
* API changes → `docs/interfaces/`
* runtime rules → `docs/governance/`

---

# Summary

To begin development:

1. Create a virtual environment
2. Install dependencies
3. validate environment configuration
4. start services
5. run tests

This ensures a consistent and stable development environment.

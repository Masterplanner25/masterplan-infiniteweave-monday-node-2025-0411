# Contributing to A.I.N.D.Y.

Thank you for your interest in contributing to this project.

This document defines the development workflow, coding expectations, and contribution process used in this repository.

The goal is to maintain a consistent, reliable engineering environment while allowing contributors to improve the system safely.

---

# Development Workflow

## Repository Structure

Key project directories:

```
docs/
  architecture/        System architecture, plugin registry, coupling rules
  runtime/             Execution contract, syscall system, OS isolation, memory, agent runtime
  apps/                Domain app documentation (ARM, Infinity Algorithm, social, search, etc.)
  platform/
    engineering/       Testing strategy, tech debt, scalability audit
    governance/        Invariants, error handling policy, changelog, release notes
    interfaces/        API and component contracts
  deployment/          Docker setup, migration policy, deployment model
  watcher/             Watcher agent setup and signal reference
  sdk/                 Python SDK reference
  nodus/               Nodus scripting language reference
  syscalls/            Syscall reference
  getting-started/     Quickstart guide
  tutorials/           End-to-end walkthroughs

AINDY/            Core system implementation
apps/             Domain app modules
client/           React frontend
tests/            Test suite
```

Architecture and behavioral expectations are defined in the documentation inside the `docs/` directory.

---

# Branch Strategy

This project uses a simple branching model.

```
main        Stable production-ready code
develop     Active development branch
feature/*   Feature development
fix/*       Bug fixes
```

Guidelines:

* `main` should always remain stable.
* All development work should branch from `develop`.
* Pull requests should target `develop` unless they are critical fixes.

Example:

```
feature/memory-bridge
feature/runtime-improvements
fix/api-validation
```

---

# Coding Standards

To maintain consistency across the codebase:

### General Principles

* Prefer **clarity over cleverness**
* Keep functions small and focused
* Avoid unnecessary complexity
* Write code that is easy to read and maintain

### Naming Conventions

Use descriptive names:

```
calculate_execution_score()
resolve_memory_context()
validate_agent_input()
```

Avoid ambiguous names like:

```
doStuff()
handleData()
processThing()
```

### File Organization

Group related functionality together.

Example:

```
AINDY/
  agents/
  runtime/
  memory/
  orchestration/
```

Each module should have a clear purpose.

---

# Pull Request Process

When submitting a pull request:

1. Create a feature branch from `dev`
2. Implement your changes
3. Add or update tests if necessary
4. Ensure the test suite passes
5. Submit a pull request to `dev`

Pull request descriptions should include:

* summary of changes
* motivation for the change
* relevant documentation updates

Example PR description:

```
Adds memory bridge caching layer.

Improves runtime performance by reducing repeated memory resolution calls.

Updates MEMORY_BRIDGE_CONTRACT.md documentation.
```

---

# Testing Requirements

All changes should be validated through tests.

Run the test suite before submitting a pull request:

```
pytest
```

Tests are located in the `tests/` directory.

When possible:

* add tests for new functionality
* avoid breaking existing tests
* ensure deterministic test behavior

---

# Documentation Requirements

This repository treats documentation as part of the system architecture.

When changing behavior related to:

* APIs
* system invariants
* runtime behavior
* architecture

update the relevant documents in:

```
docs/
```

Examples:

```
docs/platform/interfaces/API_CONTRACTS.md
docs/platform/governance/INVARIANTS.md
docs/architecture/SYSTEM_SPEC.md
docs/runtime/EXECUTION_CONTRACT.md
```

---

# Error Handling Expectations

Error handling should follow the policies defined in:

```
docs/platform/governance/ERROR_HANDLING_POLICY.md
```

Avoid introducing inconsistent exception behavior.

---

# System Invariants

The core assumptions of the system are defined in:

```
docs/platform/governance/INVARIANTS.md
```

Contributors should not introduce changes that violate these invariants without updating the documentation.

---

# Questions and Discussions

If you are unsure how a change fits into the system architecture:

1. Review the architecture documentation
2. Open a discussion or issue describing the proposed change

Architectural consistency is prioritized over rapid feature additions.

---

# Summary

Contributors should:

* follow the branching strategy
* write clear, maintainable code
* run the test suite
* update documentation when architecture changes
* respect system invariants and interface contracts

These practices help ensure the long-term stability and reliability of the project.

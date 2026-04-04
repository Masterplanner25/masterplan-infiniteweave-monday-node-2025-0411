# A.I.N.D.Y.

A.I.N.D.Y. is a FastAPI-based platform backend for versioned syscalls, Nodus execution, memory retrieval and persistence, flow orchestration, agent runs, and execution observability.

The release-facing entrypoints are the public health routes, the auth routes, and the `/platform/*` surface. The platform surface exposes:

- platform API key management
- syscall discovery and dispatch
- dynamic flow and node registration
- Nodus script execution, trace lookup, and scheduling
- tenant usage and memory address space queries

## Quick Start

For the shortest path to a live syscall, use the getting-started guide:

[Getting Started](docs/getting-started/index.md)

Local startup:

```bash
cd AINDY
docker compose up -d
```

Health check:

```bash
curl http://localhost:8000/health
```

## Core Docs

- [Getting Started](docs/getting-started/index.md)
- [API Contracts](docs/interfaces/API_CONTRACTS.md)
- [Syscall System](docs/architecture/SYSCALL_SYSTEM.md)
- [System Spec](docs/architecture/SYSTEM_SPEC.md)
- [Runtime Behavior](docs/architecture/RUNTIME_BEHAVIOR.md)
- [Execution Contract](docs/architecture/EXECUTION_CONTRACT.md)
- [Testing Strategy](docs/engineering/TESTING_STRATEGY.md)
- [Architecture Overview](AINDY_README.md)
- [Changelog](CHANGELOG.md)

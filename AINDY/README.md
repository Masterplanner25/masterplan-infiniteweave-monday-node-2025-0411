# A.I.N.D.Y.

Backend for the Masterplan Infinite Weave project.

See [`AINDY_README.md`](AINDY_README.md) for architecture overview, directory structure, and runtime notes.

## Quick Start

```bash
cd AINDY
alembic upgrade head
uvicorn main:app --reload
```

## Documentation

| Doc | Description |
|-----|-------------|
| [`AINDY_README.md`](AINDY_README.md) | Architecture overview and runtime notes |
| [`docs/architecture/SYSCALL_SYSTEM.md`](docs/architecture/SYSCALL_SYSTEM.md) | Syscall layer, ABI versioning, dispatcher pipeline |
| [`docs/architecture/MEMORY_ADDRESS_SPACE.md`](docs/architecture/MEMORY_ADDRESS_SPACE.md) | Path-addressable memory namespace |
| [`docs/architecture/OS_ISOLATION_LAYER.md`](docs/architecture/OS_ISOLATION_LAYER.md) | Tenant isolation, quota enforcement, WAIT/RESUME |
| [`docs/architecture/SYSTEM_SPEC.md`](docs/architecture/SYSTEM_SPEC.md) | Full system specification |
| [`docs/architecture/RUNTIME_BEHAVIOR.md`](docs/architecture/RUNTIME_BEHAVIOR.md) | Runtime behavior reference |
| [`docs/architecture/EXECUTION_CONTRACT.md`](docs/architecture/EXECUTION_CONTRACT.md) | Execution pipeline contract |
| [`docs/interfaces/API_CONTRACTS.md`](docs/interfaces/API_CONTRACTS.md) | Complete API surface |
| [`docs/engineering/TESTING_STRATEGY.md`](docs/engineering/TESTING_STRATEGY.md) | Test architecture and coverage policy |
| [`CHANGELOG.md`](CHANGELOG.md) | Sprint-by-sprint change history |

# memory_bridge_rs Build Quick Reference

Canonical documentation lives at:

- `docs/runtime/NATIVE_MEMORY_BRIDGE.md`

This file is only a quick-reference for local rebuilds.

## Correct paths

- Crate root: `AINDY/memory/native/memory_bridge_rs/`
- Manifest: `AINDY/memory/native/memory_bridge_rs/Cargo.toml`

## Quick rebuild

From the repo root:

```powershell
.\AINDY\memory\native\memory_bridge_rs\rebuild_native.ps1
```

Or manually:

```powershell
cargo build --release --manifest-path AINDY\memory\native\memory_bridge_rs\Cargo.toml
python -m maturin develop -m AINDY\memory\native\memory_bridge_rs\Cargo.toml --release
```

## Validation

```powershell
pytest tests\integration\test_memory_native_scorer.py -q
pytest tests\integration\test_memory_bridge.py -q
```

## Runtime control

- `USE_NATIVE_SCORER=true` enables native scoring when the extension is available
- `USE_NATIVE_SCORER=false` forces the Python fallback

See `docs/runtime/NATIVE_MEMORY_BRIDGE.md` for architecture, Docker, deployment, and failure-mode details.

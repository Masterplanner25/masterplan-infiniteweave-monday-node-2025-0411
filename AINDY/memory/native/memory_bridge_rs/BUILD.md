# Memory Bridge Native Build

This crate provides the production native scorer used by `runtime/memory/native_scorer.py`.

## Requirements

- Rust toolchain with `cargo`
- Python environment matching the app runtime
- `maturin` installed in that Python environment

## Release Build

From the repository root:

```powershell
cargo build --release --manifest-path bridge/memory_bridge_rs/Cargo.toml
python -m maturin develop -m bridge/memory_bridge_rs/Cargo.toml --release
```

## Validation

Run the focused scorer tests after rebuilding:

```powershell
pytest tests/integration/test_memory_native_scorer.py -q
```

## Runtime Control

Set `USE_NATIVE_SCORER=true` to enable the native scorer.

Set `USE_NATIVE_SCORER=false` to force the Python fallback without changing code.

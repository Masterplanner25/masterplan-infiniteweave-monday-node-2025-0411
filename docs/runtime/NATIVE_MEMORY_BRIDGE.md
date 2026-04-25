# Native Memory Bridge

The native memory bridge is an optional C++/Rust/Python extension that accelerates memory scoring and semantic similarity computation. It is used by the memory retrieval pipeline when `USE_NATIVE_SCORER=true` (the default in `AINDY/config.py`) and the native module can be imported.

---

## Architecture

Three layers communicate through FFI:

```text
Python (AINDY runtime)
    |  calls via pyo3 Python extension module
    v
Rust (memory_bridge_rs)
    |  calls via extern "C" FFI
    v
C++ (memory_cpp/semantic.cpp)
    |- cosine_similarity()
    |- weighted_dot_product()
```

**Why Rust + C++?**

- The Python boundary is implemented with `pyo3` so the extension can expose normal Python classes and functions from a `cdylib`.
- The C++ math kernels already exist in `memory_cpp/semantic.cpp`, so Rust acts as the adapter layer instead of rewriting that code path.
- `cpp_bridge.rs` takes borrowed Rust slices (`&[f64]`) and passes `as_ptr()` plus `len` into the C++ functions. That keeps the FFI surface narrow and avoids per-element marshalling at the call site.

**What the Rust layer owns**

- `MemoryNode`
- `MemoryTrace`
- `score_memory_nodes(...)`
- Input-length validation for `semantic_similarity(...)` and `weighted_dot_product(...)`

`score_memory_nodes(...)` is pure Rust. It does not call into C++; the scoring formula and usage normalization are implemented directly in `src/lib.rs`.

**What the C++ layer owns**

- `cosine_similarity(const double* a, const double* b, size_t len) -> double`
- `weighted_dot_product(const double* values, const double* weights, size_t len) -> double`

The Rust wrapper in `cpp_bridge.rs` asserts matching slice lengths before calling the `unsafe extern "C"` functions. Empty slices are handled in Rust and return `0.0` without calling C++.

---

## Python Interface

Module name: `memory_bridge_rs`

### Classes

#### `MemoryNode`

Constructor:

```python
MemoryNode(content: str, source: str | None, tags: list[str])
```

Fields exposed to Python:

- `id: str` - generated UUID v4
- `timestamp: str` - current UTC timestamp in RFC3339 format
- `content: str`
- `source: str | None`
- `tags: list[str]`
- `children: list[MemoryNode]`

Methods:

- `link(child: MemoryNode) -> None` - appends a child node
- `to_dict() -> dict` - recursive dict export including children

#### `MemoryTrace`

Constructor:

```python
MemoryTrace()
```

State:

- `root_nodes: list[MemoryNode]`

Methods:

- `add_node(node: MemoryNode) -> None`
- `export() -> list[dict]` - exports all root nodes through `MemoryNode.to_dict()`
- `find_by_tag(tag: str) -> list[dict]` - recursive tag search across the tree

### Functions

#### `semantic_similarity(a, b) -> float`

```python
semantic_similarity(a: list[float], b: list[float]) -> float
```

- Requires equal-length vectors
- Returns cosine similarity from the C++ kernel
- Output range is `[-1.0, 1.0]`
- Raises `ValueError` if lengths differ

#### `weighted_dot_product(values, weights) -> float`

```python
weighted_dot_product(values: list[float], weights: list[float]) -> float
```

- Requires equal-length vectors
- Returns the weighted dot product from the C++ kernel
- Raises `ValueError` if lengths differ

#### `score_memory_nodes(...) -> list[float]`

```python
score_memory_nodes(
    similarities: list[float],
    recencies: list[float],
    success_rates: list[float],
    usage_frequencies: list[float],
    graph_bonuses: list[float],
    impact_scores: list[float],
    trace_bonuses: list[float],
    low_value_flags: list[bool],
) -> list[float]
```

All input lists must be the same length or the function raises `ValueError`.

For each node, the Rust scorer computes:

```text
success_weight = 0.25 if usage_frequency > 5.0 else 0.20
impact_bonus   = clamp(impact_score / 5.0, 0.0, 1.0) * 0.15
normalized_usage = clamp(log(1 + usage_frequency) / log(101), 0.0, 1.0)

score =
    similarities      * 0.40
  + recencies         * 0.15
  + success_rates     * success_weight
  + normalized_usage  * 0.10
  + graph_bonuses     * 0.15
  + impact_bonus
  + trace_bonuses

if low_value_flag:
    score *= 0.5
```

`normalize_usage(...)` uses natural log scale and caps the result to `[0.0, 1.0]` with `log1p(value) / log(101)`.

---

## Runtime Control

```text
USE_NATIVE_SCORER=true   # default
USE_NATIVE_SCORER=false  # force Python fallback
```

Current behavior is split across two places:

- `AINDY/config.py` defines `USE_NATIVE_SCORER: bool = True`
- `AINDY/runtime/memory/native_scorer.py` actually checks `os.getenv("USE_NATIVE_SCORER", "true")`

The fallback scorer lives in `AINDY/runtime/memory/scorer.py`.

Runtime flow:

1. `MemoryScorer._score_nodes()` calls `AINDY/runtime/memory/native_scorer.py::score_memory_nodes(...)`
2. The native scorer checks whether native scoring is enabled
3. It lazily imports `memory_bridge_rs` from `target/release` or `target/debug`
4. If the module is disabled, unavailable, or raises at runtime, it returns a fallback result
5. `scorer.py` then computes scores in pure Python with `_score_node_python(...)`

The Python fallback implements the same coefficients and the same usage normalization formula as the Rust scorer. The practical difference is performance, not scoring semantics.

The native bridge is therefore optional at runtime. If it is not built, the scorer still works.

---

## Build Requirements

| Tool | Version | Purpose |
|---|---|---|
| Rust toolchain | 1.70+ | Compile Rust crate |
| cargo | bundled with Rust | Build system |
| maturin | 1.x | Build Python extension from Rust |
| C++ compiler | GCC/Clang/MSVC | Compile `semantic.cpp` via `cc` crate |
| Python | 3.11+ | Target Python environment |

Notes from the crate configuration:

- `pyo3 = 0.19`
- crate type is `cdylib`
- `build.rs` compiles `memory_cpp/semantic.cpp`

---

## Build Instructions

### Linux / macOS

```bash
# Install Rust (if not installed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install maturin into the project's Python environment
pip install maturin

# Build and install the extension
cd AINDY/memory/native/memory_bridge_rs
maturin develop --release

# Or from the repo root:
maturin develop \
  --manifest-path AINDY/memory/native/memory_bridge_rs/Cargo.toml \
  --release
```

### Windows (PowerShell)

```powershell
# Run the helper script from the repo root:
.\AINDY\memory\native\memory_bridge_rs\rebuild_native.ps1

# Or manually:
cd AINDY\memory\native\memory_bridge_rs
cargo build --release
python -m maturin develop -m Cargo.toml --release
```

### Docker

Single-stage example:

```dockerfile
FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

RUN pip install maturin

WORKDIR /app
COPY . .

RUN maturin develop \
    --manifest-path AINDY/memory/native/memory_bridge_rs/Cargo.toml \
    --release
```

Multi-stage example:

```dockerfile
FROM python:3.11-slim AS native-builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app
COPY . .
RUN pip install maturin \
    && maturin build \
        --manifest-path AINDY/memory/native/memory_bridge_rs/Cargo.toml \
        --release

FROM python:3.11-slim

WORKDIR /app
COPY . .
COPY --from=native-builder /app/AINDY/memory/native/memory_bridge_rs/target/wheels /tmp/wheels

RUN pip install /tmp/wheels/*.whl \
    && rm -rf /tmp/wheels
```

`maturin develop` installs directly into the active Python environment. `maturin build` produces a wheel that can be installed into the runtime image.

---

## Validation

After building, verify the extension loads and produces correct output:

```python
import memory_bridge_rs

score = memory_bridge_rs.semantic_similarity([1.0, 0.0], [1.0, 0.0])
assert abs(score - 1.0) < 1e-6, f"Expected 1.0, got {score}"

score = memory_bridge_rs.semantic_similarity([1.0, 0.0], [0.0, 1.0])
assert abs(score - 0.0) < 1e-6, f"Expected 0.0, got {score}"

print("Native bridge OK")
```

Focused tests that exist in this repository:

```bash
pytest tests/integration/test_memory_native_scorer.py -q
pytest tests/integration/test_memory_bridge.py -q
```

`tests/integration/test_memory_bridge.py` skips the Rust-extension section when `memory_bridge_rs` is not compiled.

---

## Failure Modes and Recovery

### Import failure on first use

`AINDY/runtime/memory/native_scorer.py` imports `memory_bridge_rs` lazily the first time `score_memory_nodes(...)` runs. Import does not happen at module import time.

- **Effect**: `native_scorer.py` returns `{"scores": None, "engine": "python", "fallback_used": True, "error": "unavailable"}` and `AINDY/runtime/memory/scorer.py` computes scores in pure Python.
- **Detection**: log line from `AINDY/runtime/memory/native_scorer.py` similar to `[MemoryNativeScorer] native bridge unavailable: ...`
- **Recovery**: set `USE_NATIVE_SCORER=false` to force the Python path, or rebuild the extension so `memory_bridge_rs` becomes importable

### Native scorer disabled

- **Effect**: the native scorer is bypassed intentionally and the Python scorer is used
- **Detection**: `native_scorer.py` reports fallback reason `disabled`
- **Recovery**: unset `USE_NATIVE_SCORER=false` or set `USE_NATIVE_SCORER=true`

### Runtime exception inside the native module

- **Effect**: `native_scorer.py` logs a warning, increments its error counter, and falls back to the Python scorer for that call
- **Detection**: warning log `[MemoryNativeScorer] native scoring failed, falling back to Python: ...`
- **Recovery**: leave the process running on the Python fallback or disable native scoring explicitly while investigating

### Wrong Python version

The extension is built against the Python ABI used by `maturin`.

- **Detection**: `ImportError` when importing `memory_bridge_rs` even though the build completed on another interpreter
- **Recovery**: rebuild the extension with the same Python version used by the runtime process

### C++ compiler missing

`build.rs` invokes the `cc` crate, which then calls the system C++ compiler.

- **Detection**: `cargo build` or `maturin develop` fails during the `build.rs` phase with a compiler lookup error
- **Recovery (Linux)**: install `build-essential` or `gcc-c++`
- **Recovery (macOS)**: run `xcode-select --install`
- **Recovery (Windows)**: install Visual Studio Build Tools with the C++ workload

### Segfault or incorrect results

The Rust wrappers assert length equality before calling C++, but the FFI call itself is still `unsafe`.

- **Detection**: process crash, native abort, or mathematically incorrect output from the validation script
- **Recovery**: set `USE_NATIVE_SCORER=false` to bypass the extension and investigate `AINDY/memory/native/memory_bridge_rs/memory_cpp/semantic.cpp`

---

## Deployment Notes

### CI/CD

The current GitHub Actions workflow in `.github/workflows/ci.yml` does not install Rust, `cargo`, or `maturin`, and it does not build `memory_bridge_rs`.

That means test environments rely on the Python fallback because the native module is unavailable, not because CI explicitly disables `USE_NATIVE_SCORER`.

If native coverage is needed in CI, add a dedicated job that installs Rust and builds the extension before running the native bridge tests.

Example:

```yaml
native-scorer-test:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: dtolnay/rust-toolchain@stable
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"
    - run: pip install maturin pytest
    - run: maturin develop --manifest-path AINDY/memory/native/memory_bridge_rs/Cargo.toml --release
    - run: pytest tests/integration/test_memory_native_scorer.py tests/integration/test_memory_bridge.py -q
```

### Production deployment

- Build the extension during image build, not at container start
- Keep the build Python and runtime Python versions aligned
- Prefer a multi-stage image so Rust and the C++ toolchain stay out of the final runtime layer
- If the extension is not present at runtime, the system still works through the Python fallback path in `AINDY/runtime/memory/scorer.py`

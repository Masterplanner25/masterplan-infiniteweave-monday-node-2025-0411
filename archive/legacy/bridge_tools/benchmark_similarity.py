"""
Benchmark: C++ kernel vs pure Python cosine similarity and weighted dot product.
Run from the AINDY directory with venv activated:
    python bridge/benchmark_similarity.py
"""
import time
import math
import random


# --- Pure Python implementations (reference baseline) ---

def python_cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    denom = mag_a * mag_b
    return dot / denom if denom > 1e-15 else 0.0


def python_weighted_dot(values, weights):
    return sum(v * w for v, w in zip(values, weights))


def _load_cpp_kernel():
    try:
        from memory_bridge_rs import semantic_similarity as cpp_cosine
        from memory_bridge_rs import weighted_dot_product as cpp_weighted_dot
        return True, cpp_cosine, cpp_weighted_dot
    except ImportError:
        print("WARNING: C++ kernel not available — skipping comparison")
        return False, None, None


def _benchmark(label, fn, *args, iterations=10_000):
    start = time.perf_counter()
    for _ in range(iterations):
        fn(*args)
    elapsed = time.perf_counter() - start
    per_call_ms = elapsed / iterations * 1000
    print(f"{label:<28} {elapsed:.3f}s total   {per_call_ms:.4f}ms/call   ({iterations:,} iters)")
    return elapsed


def main():
    has_cpp, cpp_cosine, cpp_weighted_dot = _load_cpp_kernel()

    # --- Cosine similarity benchmark ---
    # DIM = 1536 matches OpenAI text-embedding-ada-002 dimensions,
    # the expected embedding size when semantic memory search is added to A.I.N.D.Y.
    dim = 1536
    iterations = 10_000

    rng = random.Random(42)
    vec_a = [rng.gauss(0, 1) for _ in range(dim)]
    vec_b = [rng.gauss(0, 1) for _ in range(dim)]

    print(f"\n=== Cosine Similarity  (dim={dim}, {iterations:,} iterations) ===")
    py_time = _benchmark("Pure Python          :", python_cosine, vec_a, vec_b,
                          iterations=iterations)
    if has_cpp:
        cpp_time = _benchmark("C++ kernel           :", cpp_cosine, vec_a, vec_b,
                               iterations=iterations)
        speedup = py_time / cpp_time
        print(f"\nSpeedup: {speedup:.1f}x faster than pure Python")

        py_result = python_cosine(vec_a, vec_b)
        cpp_result = cpp_cosine(vec_a, vec_b)
        assert abs(py_result - cpp_result) < 1e-9, \
            f"Results diverge: py={py_result} cpp={cpp_result}"
        print("Result verification: PASS (results match within 1e-9)")

    # --- Weighted dot product benchmark (Infinity Algorithm engagement score) ---
    engagement_iters = 100_000
    # Typical A.I.N.D.Y. engagement inputs
    interactions = [float(rng.randint(0, 1000)) for _ in range(5)]
    weights = [2.0, 3.0, 1.5, 1.0, 0.5]

    print(f"\n=== Weighted Dot Product  (dim=5, {engagement_iters:,} iterations) ===")
    py_time_wd = _benchmark("Pure Python          :", python_weighted_dot,
                             interactions, weights, iterations=engagement_iters)
    if has_cpp:
        cpp_time_wd = _benchmark("C++ kernel           :", cpp_weighted_dot,
                                  interactions, weights, iterations=engagement_iters)
        speedup_wd = py_time_wd / cpp_time_wd
        print(f"\nSpeedup: {speedup_wd:.1f}x faster than pure Python")

        py_wd = python_weighted_dot(interactions, weights)
        cpp_wd = cpp_weighted_dot(interactions, weights)
        assert abs(py_wd - cpp_wd) < 1e-9, \
            f"Results diverge: py={py_wd} cpp={cpp_wd}"
        print("Result verification: PASS (results match within 1e-9)")

    print("\n=== Summary ===")
    print(f"C++ kernel active  : {has_cpp}")
    print("MSVC toolchain     : VS 2022 (x64)")
    print("Build mode         : debug (dev profile)")


if __name__ == "__main__":
    main()

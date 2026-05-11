// A.I.N.D.Y. C++ Bridge
// Direct extern "C" FFI — no proc-macro crates required.
// All unsafe C++ calls are contained in this module; callers use the safe wrappers below.

extern "C" {
    // Core cosine similarity — foundation for semantic memory node search.
    // When embeddings are stored on MemoryNode, this kernel does the comparison.
    fn cosine_similarity(a: *const f64, b: *const f64, len: usize) -> f64;

    // Weighted dot product — maps directly to the Infinity Algorithm engagement score.
    // values  = [likes, shares, comments, clicks, time_on_page]
    // weights = [2.0,   3.0,    1.5,     1.0,    0.5]
    fn weighted_dot_product(values: *const f64, weights: *const f64, len: usize) -> f64;
}

/// Compute cosine similarity between two equal-length f64 slices.
/// Calls into the C++ kernel via extern "C" FFI.
/// Panics if slices are different lengths.
pub fn compute_similarity(a: &[f64], b: &[f64]) -> f64 {
    assert_eq!(
        a.len(),
        b.len(),
        "Vectors must be same length for cosine similarity"
    );
    if a.is_empty() {
        return 0.0;
    }
    unsafe { cosine_similarity(a.as_ptr(), b.as_ptr(), a.len()) }
}

/// Compute weighted dot product of two equal-length f64 slices.
/// Calls into the C++ kernel via extern "C" FFI.
/// Panics if slices are different lengths.
pub fn compute_weighted_dot(values: &[f64], weights: &[f64]) -> f64 {
    assert_eq!(
        values.len(),
        weights.len(),
        "Vectors must be same length for weighted dot product"
    );
    if values.is_empty() {
        return 0.0;
    }
    unsafe { weighted_dot_product(values.as_ptr(), weights.as_ptr(), values.len()) }
}

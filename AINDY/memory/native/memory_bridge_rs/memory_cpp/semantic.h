#pragma once
#include <cstddef>

// A.I.N.D.Y. Semantic Engine — C++ declarations
// extern "C" linkage so Rust can call these via direct FFI without cxx proc-macros.

#ifdef __cplusplus
extern "C" {
#endif

/// Cosine similarity between two f64 vectors.
/// Returns a value in [-1.0, 1.0]; returns 0.0 for empty or zero-magnitude vectors.
/// Epsilon guard (1e-9) prevents division by zero.
double cosine_similarity(const double* a, const double* b, size_t len);

/// Weighted dot product: sum(values[i] * weights[i]) for i in [0, len).
/// Used by the Infinity Algorithm engagement score formula:
///   score = weighted_dot_product(interactions, weights) / total_views
///   where interactions = [likes, shares, comments, clicks, time_on_page]
///         weights      = [2.0,  3.0,    1.5,     1.0,   0.5]
double weighted_dot_product(const double* values, const double* weights, size_t len);

#ifdef __cplusplus
}
#endif

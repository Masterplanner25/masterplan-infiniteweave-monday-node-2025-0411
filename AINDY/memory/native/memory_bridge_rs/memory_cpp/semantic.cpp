// A.I.N.D.Y. Semantic Engine — C++ Core
// High-performance vector math for the Infinity Algorithm
// Called via Rust cxx FFI from memory_bridge_rs
//
// Formula references:
// Weighted signal score = (historical impact x ai_utilization x time_spent) / difficulty
// Historical impact = time_spent x complexity x confidence_level
//
// Engagement Score (direct weighted dot product):
//   score = (likes*2 + shares*3 + comments*1.5 + clicks*1 + time_on_page*0.5)
//           / total_views
//   This is exactly: weighted_dot_product(interactions, weights) / total_views

#include "semantic.h"
#include <cmath>

double cosine_similarity(const double* a, const double* b, size_t len) {
    if (len == 0) return 0.0;

    double dot   = 0.0;
    double mag_a = 0.0;
    double mag_b = 0.0;

    for (size_t i = 0; i < len; ++i) {
        dot   += a[i] * b[i];
        mag_a += a[i] * a[i];
        mag_b += b[i] * b[i];
    }

    double denom = std::sqrt(mag_a) * std::sqrt(mag_b);
    // Guard: return 0.0 if either vector is zero-magnitude (avoids division by zero)
    // Threshold 1e-15 is well below any meaningful vector magnitude.
    if (denom < 1e-15) return 0.0;
    return dot / denom;
}

double weighted_dot_product(const double* values, const double* weights, size_t len) {
    if (len == 0) return 0.0;

    double sum = 0.0;
    for (size_t i = 0; i < len; ++i) {
        sum += values[i] * weights[i];
    }
    return sum;
}

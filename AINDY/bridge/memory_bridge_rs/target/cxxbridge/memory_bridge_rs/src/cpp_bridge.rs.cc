#include "memory_cpp/semantic.h"
#include <cstddef>

#ifdef __GNUC__
#pragma GCC diagnostic ignored "-Wmissing-declarations"
#ifdef __clang__
#pragma clang diagnostic ignored "-Wdollar-in-identifier-extension"
#endif // __clang__
#endif // __GNUC__

extern "C" {
double cxxbridge1$194$cosine_similarity(double const *a, double const *b, ::std::size_t len) noexcept {
  double (*cosine_similarity$)(double const *, double const *, ::std::size_t) = ::cosine_similarity;
  return cosine_similarity$(a, b, len);
}

double cxxbridge1$194$weighted_dot_product(double const *values, double const *weights, ::std::size_t len) noexcept {
  double (*weighted_dot_product$)(double const *, double const *, ::std::size_t) = ::weighted_dot_product;
  return weighted_dot_product$(values, weights, len);
}
} // extern "C"

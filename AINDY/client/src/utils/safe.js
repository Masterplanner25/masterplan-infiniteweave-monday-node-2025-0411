export function safeArray(value) {
  if (Array.isArray(value)) return value;
  if (value === null || value === undefined) return [];
  return [];
}

export function safeMap(value, fn) {
  if (!Array.isArray(value)) {
    console.warn("safeMap prevented crash. Value:", value);
    return [];
  }
  return value.map(fn);
}

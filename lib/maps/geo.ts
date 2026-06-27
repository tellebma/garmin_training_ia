/**
 * Shared geographic type guards used across map utilities.
 */

/**
 * Returns true when `value` is a valid [longitude, latitude] pair:
 * a two-element (or longer) array of finite numbers.
 */
export function isLngLat(value: unknown): value is [number, number] {
  return (
    Array.isArray(value) &&
    value.length >= 2 &&
    typeof value[0] === 'number' &&
    typeof value[1] === 'number' &&
    Number.isFinite(value[0]) &&
    Number.isFinite(value[1])
  )
}

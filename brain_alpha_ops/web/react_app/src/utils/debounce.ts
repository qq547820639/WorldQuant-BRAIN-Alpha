/**
 * Debounce utility functions for React applications
 */

/**
 * Creates a debounced version of a function that delays invoking
 * the function until after the specified delay.
 *
 * @param fn - The function to debounce
 * @param delay - The delay in milliseconds (default: 300)
 * @returns A debounced version of the function
 */
export function debounce<T extends (...args: Parameters<T>) => ReturnType<T>>(
  fn: T,
  delay: number = 300
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  return function (...args: Parameters<T>) {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }

    timeoutId = setTimeout(() => {
      fn(...args);
      timeoutId = null;
    }, delay);
  };
}

/**
 * Creates a throttled version of a function that only invokes
 * the function at most once per specified delay.
 *
 * @param fn - The function to throttle
 * @param limit - The time limit in milliseconds (default: 300)
 * @returns A throttled version of the function
 */
export function throttle<T extends (...args: Parameters<T>) => ReturnType<T>>(
  fn: T,
  limit: number = 300
): (...args: Parameters<T>) => void {
  let inThrottle = false;

  return function (...args: Parameters<T>) {
    if (!inThrottle) {
      fn(...args);
      inThrottle = true;
      setTimeout(() => {
        inThrottle = false;
      }, limit);
    }
  };
}

/**
 * Cleans up any pending timeout (useful for cleanup in useEffect)
 * @param timeoutId - The timeout ID to clear
 */
export function clearDebounce(timeoutId: ReturnType<typeof setTimeout> | null): void {
  if (timeoutId) {
    clearTimeout(timeoutId);
  }
}

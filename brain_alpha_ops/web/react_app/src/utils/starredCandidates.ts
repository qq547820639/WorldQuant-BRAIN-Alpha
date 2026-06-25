/**
 * LocalStorage-based candidate star/favorite management.
 *
 * Stores a Set of starred candidate alpha_ids in localStorage
 * under the key "brain_alpha_starred_candidates".
 */

const STORAGE_KEY = 'brain_alpha_starred_candidates';

/** Read starred alpha_ids from localStorage. Returns a Set of strings. */
export function getStarred(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return new Set(parsed.map(String).filter(Boolean));
    }
    return new Set();
  } catch {
    return new Set();
  }
}

/** Toggle the star status of an alpha_id. Returns the new starred state. */
export function toggleStar(alphaId: string): boolean {
  const starred = getStarred();
  const isCurrentlyStarred = starred.has(alphaId);
  if (isCurrentlyStarred) {
    starred.delete(alphaId);
  } else {
    starred.add(alphaId);
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...starred]));
  } catch {
    console.warn('starredCandidates: localStorage full or unavailable');
  }
  return !isCurrentlyStarred;
}

/** Check if an alpha_id is starred. */
export function isStarred(alphaId: string): boolean {
  return getStarred().has(alphaId);
}

/** Get the count of starred candidates. */
export function getStarredCount(): number {
  return getStarred().size;
}

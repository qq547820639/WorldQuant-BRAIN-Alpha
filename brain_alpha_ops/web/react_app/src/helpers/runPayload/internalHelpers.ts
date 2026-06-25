/** Internal helper functions for job state classification.
 *
 *  These helpers are not re-exported from the package index; they exist only
 *  to be shared across the submodules inside `runPayload/`. */

import { isRecord } from '@/types';

export function record(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

export function textField(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

export function truthyField(...values: unknown[]): boolean {
  return values.some((value) => value === true);
}

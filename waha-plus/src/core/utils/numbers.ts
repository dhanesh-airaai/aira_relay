/**
 * Number utilities
 * Extracted from noweb engine for shared use
 */

import Long from 'long';

const isObjectALong = (value: any): value is Long => {
  return (
    value &&
    typeof value === 'object' &&
    'low' in value &&
    'high' in value &&
    'unsigned' in value
  );
};

const toNumber = (longValue: Long): number => {
  const { low, high, unsigned } = longValue;
  const result = unsigned ? low >>> 0 : low + high * 0x100000000;
  return result;
};

export function ensureNumber(value: number | Long | string | null): number {
  if (!value) {
    // @ts-ignore
    return value;
  }
  if (typeof value === 'string') {
    return Number.parseInt(value, 10);
  }
  if (isObjectALong(value)) {
    return toNumber(value);
  }
  // number
  return value;
}

import { describe, expect, it } from 'vitest';
import { formatBytes } from './api.js';

describe('formatBytes', () => {
  it('formats storage sizes', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(1024 ** 3)).toBe('1.0 GB');
  });
});

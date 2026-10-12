import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';

// Auto-cleanup between tests (required because vitest globals are off).
afterEach(() => {
  cleanup();
});

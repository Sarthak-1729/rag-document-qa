import axe from 'axe-core';
import { expect, vi } from 'vitest';
import { ApiError } from '../api/client.js';

export const DOC = {
  id: 'doc-1',
  filename: 'nature.pdf',
  pages: 3,
  chunks: 3,
  uploaded_at: '2026-10-28T10:00:00Z',
};

export const ANSWER = {
  answer: 'Volcanoes erupt when pressure builds [1]. Lava flows down [1][2].',
  sources: [
    { n: 1, doc_id: 'doc-1', doc: 'nature.pdf', page: 2, text: 'Magma rises through cracks.' },
    { n: 2, doc_id: 'doc-1', doc: 'nature.pdf', page: 3, text: 'Lava flows down its slopes.' },
  ],
  refused: false,
  refusal_reason: null,
};

export const REFUSAL = { answer: "I don't know.", sources: [], refused: true, refusal_reason: 'model' };

// A fake of src/api/client.js `api`; override any method per test.
export function fakeApi(overrides = {}) {
  return {
    health: vi.fn().mockResolvedValue({ status: 'ok', llm_provider: 'gemini', documents: 1 }),
    listDocuments: vi.fn().mockResolvedValue([DOC]),
    deleteDocument: vi.fn().mockResolvedValue(null),
    ask: vi.fn().mockResolvedValue(ANSWER),
    uploadDocument: vi.fn().mockResolvedValue(DOC),
    ...overrides,
  };
}

export const apiError = (status, detail = 'server detail', retryAfter = null) =>
  new ApiError(status, detail, retryAfter);

// A promise you resolve/reject from the test, to observe in-between (loading) states.
export function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

export function pdfFile(name = 'nature.pdf') {
  return new File(['%PDF-1.4 test'], name, { type: 'application/pdf' });
}

// jsdom can't compute colors, so contrast is checked in a real browser instead.
export async function expectNoAxeViolations(container) {
  const results = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
  const summary = results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(', ')}`);
  expect(summary).toEqual([]);
}

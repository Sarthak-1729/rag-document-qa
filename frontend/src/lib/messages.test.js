import { describe, expect, it } from 'vitest';
import { apiError } from '../test/helpers.js';
import { askErrorMessage, refusalExplanation, uploadErrorMessage } from './messages.js';

describe('uploadErrorMessage', () => {
  it.each([
    [0, 'Server unreachable'],
    [409, 'Already uploaded'],
    [413, 'File too large'],
    [415, 'Not a PDF'],
    [422, "Couldn't read this PDF"],
    [500, 'Upload failed'],
  ])('maps HTTP %i to "%s"', (status, title) => {
    expect(uploadErrorMessage(apiError(status)).title).toBe(title);
  });

  it('includes the server detail and explains scanned PDFs', () => {
    const message = uploadErrorMessage(apiError(422, "'scan.pdf': No extractable text."));
    expect(message.text).toContain("'scan.pdf': No extractable text.");
    expect(message.text).toMatch(/scanned/i);
  });
});

describe('askErrorMessage', () => {
  it.each([
    [0, 'Server unreachable'],
    [409, 'No documents yet'],
    [422, 'Check your question'],
    [429, 'Too many questions'],
    [502, 'The AI model had a problem'],
    [503, 'AI service unavailable'],
    [504, 'The AI model took too long'],
    [500, 'Something went wrong'],
  ])('maps HTTP %i to "%s"', (status, title) => {
    expect(askErrorMessage(apiError(status)).title).toBe(title);
  });

  it('shows Retry-After seconds on 429, with correct plural', () => {
    expect(askErrorMessage(apiError(429, '', 12)).text).toBe('Please wait 12 seconds and try again.');
    expect(askErrorMessage(apiError(429, '', 1)).text).toBe('Please wait 1 second and try again.');
    expect(askErrorMessage(apiError(429)).text).toBe('Please wait a moment and try again.');
  });

  it('falls back safely when the error has no status', () => {
    expect(askErrorMessage(new Error('boom')).title).toBe('Something went wrong');
  });
});

describe('refusalExplanation', () => {
  it('has a distinct explanation per reason', () => {
    const texts = ['low_relevance', 'model', 'uncited'].map(refusalExplanation);
    expect(new Set(texts).size).toBe(3);
  });
});

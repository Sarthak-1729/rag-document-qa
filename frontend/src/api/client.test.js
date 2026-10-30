import { afterEach, describe, expect, it, vi } from 'vitest';
import { API_URL, ApiError, api } from './client.js';

function mockFetch(status, body, headers = {}) {
  const response = new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers,
  });
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue(response);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('api client', () => {
  it('posts the question as JSON and returns the body', async () => {
    const fetch = mockFetch(200, { answer: 'ok', sources: [] });
    await expect(api.ask('Why?')).resolves.toEqual({ answer: 'ok', sources: [] });
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe(`${API_URL}/ask`);
    expect(options.method).toBe('POST');
    expect(JSON.parse(options.body)).toEqual({ question: 'Why?' });
  });

  it('turns error responses into ApiError with status, detail and Retry-After', async () => {
    mockFetch(429, { detail: 'Too many' }, { 'Retry-After': '17' });
    const error = await api.ask('q').catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 429, detail: 'Too many', retryAfter: 17 });
  });

  it('flattens FastAPI validation errors into one message', async () => {
    mockFetch(422, { detail: [{ msg: 'String too long' }, { msg: 'Field required' }] });
    const error = await api.ask('q').catch((e) => e);
    expect(error.detail).toBe('String too long Field required');
  });

  it('reports network failures as status 0', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    const error = await api.listDocuments().catch((e) => e);
    expect(error.status).toBe(0);
    expect(error.detail).toContain("Can't reach the server");
  });

  it('handles 204 No Content on delete and encodes the id', async () => {
    const fetch = mockFetch(204);
    await expect(api.deleteDocument('a/b')).resolves.toBeNull();
    expect(fetch.mock.calls[0][0]).toBe(`${API_URL}/documents/a%2Fb`);
  });
});

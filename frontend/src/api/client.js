// Thin wrapper around the backend API. Every failure becomes an ApiError with an HTTP
// status (0 = network error) so the UI can choose a friendly message.

export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8001').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(status, detail, retryAfter = null) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.retryAfter = retryAfter; // seconds, from the Retry-After header on 429
  }
}

function detailFrom(body, status) {
  const detail = body?.detail;
  if (typeof detail === 'string') return detail;
  // FastAPI validation errors (422) come back as a list of objects.
  if (Array.isArray(detail)) return detail.map((d) => d.msg).filter(Boolean).join(' ');
  return `Request failed (HTTP ${status}).`;
}

function parseJson(text) {
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return null;
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, options);
  } catch {
    throw new ApiError(0, `Can't reach the server at ${API_URL}.`);
  }
  const body = parseJson(await response.text());
  if (!response.ok) {
    const retryAfter = Number(response.headers.get('Retry-After')) || null;
    throw new ApiError(response.status, detailFrom(body, response.status), retryAfter);
  }
  return body;
}

// fetch() can't report upload progress, so uploads use XMLHttpRequest.
function uploadDocument(file, onProgress = () => {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append('files', file, file.name);

    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    });
    xhr.addEventListener('load', () => {
      const body = parseJson(xhr.responseText);
      if (xhr.status >= 200 && xhr.status < 300) resolve(body[0]);
      else reject(new ApiError(xhr.status, detailFrom(body, xhr.status)));
    });
    xhr.addEventListener('error', () =>
      reject(new ApiError(0, `Can't reach the server at ${API_URL}.`)),
    );

    xhr.open('POST', `${API_URL}/documents`);
    xhr.send(form);
  });
}

export const api = {
  health: () => request('/health'),
  listDocuments: () => request('/documents'),
  deleteDocument: (id) => request(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  ask: (question) =>
    request('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    }),
  uploadDocument,
};

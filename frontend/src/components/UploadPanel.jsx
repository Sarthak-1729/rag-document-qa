import { useId, useRef, useState } from 'react';
import { uploadErrorMessage } from '../lib/messages.js';

function isPdf(file) {
  return file.name.toLowerCase().endsWith('.pdf');
}

// Uploads selected PDFs one request per file, so one bad file doesn't block the others
// and each file gets its own progress bar and error.
export default function UploadPanel({ uploadDocument, onUploaded }) {
  const inputId = useId();
  const hintId = useId();
  const inputRef = useRef(null);
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState('');

  const update = (key, patch) =>
    setItems((current) => current.map((item) => (item.key === key ? { ...item, ...patch } : item)));

  async function handleSubmit(event) {
    event.preventDefault();
    if (busy) return;
    const files = Array.from(inputRef.current?.files ?? []);
    if (files.length === 0) {
      setSummary('Choose at least one PDF file first.');
      inputRef.current?.focus();
      return;
    }

    const batch = files.map((file, i) => ({
      key: `${Date.now()}-${i}`,
      name: file.name,
      file,
      status: 'uploading',
      progress: 0,
    }));
    setItems(batch.map(({ file, ...rest }) => rest));
    setBusy(true);
    setSummary(`Uploading ${files.length} file${files.length === 1 ? '' : 's'}…`);

    let ok = 0;
    for (const { key, file } of batch) {
      if (!isPdf(file)) {
        update(key, {
          status: 'error',
          message: { title: 'Not a PDF', text: 'Only .pdf files can be uploaded.' },
        });
        continue;
      }
      try {
        const doc = await uploadDocument(file, (progress) => update(key, { progress }));
        update(key, { status: 'done', progress: 100, doc });
        onUploaded(doc);
        ok += 1;
      } catch (error) {
        update(key, { status: 'error', message: uploadErrorMessage(error) });
      }
    }

    const failed = files.length - ok;
    setSummary(
      `Upload finished: ${ok} added${failed ? `, ${failed} failed (details below)` : ''}.`,
    );
    setBusy(false);
    if (inputRef.current) inputRef.current.value = '';
  }

  return (
    <section className="panel" aria-labelledby="upload-heading">
      <h2 id="upload-heading">Upload PDFs</h2>
      <form onSubmit={handleSubmit} noValidate>
        <label htmlFor={inputId} className="field-label">
          Choose PDF files
        </label>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept=".pdf,application/pdf"
          multiple
          aria-describedby={hintId}
        />
        <p id={hintId} className="hint">
          PDFs with selectable text. Scanned images and password-protected files can't be read.
        </p>
        <button type="submit" className="button" aria-disabled={busy || undefined}>
          {busy ? 'Uploading…' : 'Upload'}
        </button>
      </form>

      <p role="status" className="upload-summary">
        {summary}
      </p>

      {items.length > 0 && (
        <ul className="upload-list" aria-label="Upload results">
          {items.map((item) => (
            <li key={item.key} className={`upload-item upload-${item.status}`}>
              <span className="upload-name">{item.name}</span>
              {item.status === 'uploading' && (
                <progress max="100" value={item.progress} aria-label={`Uploading ${item.name}`}>
                  {item.progress}%
                </progress>
              )}
              {item.status === 'done' && (
                <span className="status-text">
                  <span aria-hidden="true">✓ </span>Added ({item.doc?.pages} pages)
                </span>
              )}
              {item.status === 'error' && (
                <span className="status-text">
                  <span aria-hidden="true">✕ </span>
                  <strong>Error: {item.message.title}.</strong> {item.message.text}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

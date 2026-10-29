export default function DocumentList({ documents, loading, error, onDelete, deletingId, headingRef }) {
  return (
    <section className="panel" aria-labelledby="documents-heading">
      {/* tabIndex -1 lets focus land here after a delete removes the focused button. */}
      <h2 id="documents-heading" ref={headingRef} tabIndex={-1}>
        Your documents
      </h2>
      {loading && <p>Loading documents…</p>}
      {error && (
        <p className="notice notice-error">
          <span aria-hidden="true">⚠ </span>
          <strong>Error:</strong> {error}
        </p>
      )}
      {!loading && !error && documents.length === 0 && (
        <p className="hint">No documents yet. Upload a PDF to get started.</p>
      )}
      {documents.length > 0 && (
        <ul className="document-list">
          {documents.map((doc) => (
            <li key={doc.id} className="document-item">
              <div>
                <span className="document-name">{doc.filename}</span>
                <span className="hint">
                  {doc.pages} page{doc.pages === 1 ? '' : 's'} · {doc.chunks} passages
                </span>
              </div>
              <button
                type="button"
                className="button button-secondary"
                onClick={() => onDelete(doc)}
                aria-disabled={deletingId === doc.id || undefined}
                aria-label={`Delete ${doc.filename}`}
              >
                {deletingId === doc.id ? 'Deleting…' : 'Delete'}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

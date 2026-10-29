import { useEffect, useRef } from 'react';

export default function SourcePanel({ source, onClose }) {
  const ref = useRef(null);

  // On narrow screens the panel sits below the chat: bring it into view when it changes.
  useEffect(() => {
    if (source) ref.current?.scrollIntoView?.({ block: 'nearest' });
  }, [source]);

  return (
    <aside id="source-panel" ref={ref} className="panel source-panel" aria-labelledby="source-heading">
      <h2 id="source-heading">Source passage</h2>
      {source ? (
        <>
          <dl className="source-meta">
            <div>
              <dt>Citation</dt>
              <dd>[{source.n}]</dd>
            </div>
            <div>
              <dt>Document</dt>
              <dd>{source.doc}</dd>
            </div>
            <div>
              <dt>PDF page</dt>
              <dd>{source.page}</dd>
            </div>
          </dl>
          <blockquote className="source-text">{source.text}</blockquote>
          <button type="button" className="button button-secondary" onClick={onClose}>
            Close source
          </button>
        </>
      ) : (
        <p className="hint">Select a citation like [1] in an answer to read the passage it came from.</p>
      )}
    </aside>
  );
}

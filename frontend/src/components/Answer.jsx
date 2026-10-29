import { splitAnswer } from '../lib/citations.js';
import { REFUSAL_TITLE, refusalExplanation } from '../lib/messages.js';

function CitationButton({ source, expanded, onToggle, children, className }) {
  return (
    <button
      type="button"
      className={className}
      aria-expanded={expanded}
      aria-controls="source-panel"
      aria-label={`Source ${source.n}: ${source.doc}, page ${source.page}`}
      onClick={(event) => onToggle(source.n, event.currentTarget)}
    >
      {children}
    </button>
  );
}

export default function Answer({ turn, activeN, onToggleSource }) {
  if (turn.status === 'pending') {
    return (
      <p className="answer-pending">
        <span className="spinner" aria-hidden="true" />
        Searching your documents…
      </p>
    );
  }

  if (turn.status === 'error') {
    return (
      <div className="notice notice-error">
        <p>
          <span aria-hidden="true">⚠ </span>
          <strong>Error: {turn.error.title}.</strong> {turn.error.text}
        </p>
      </div>
    );
  }

  if (turn.status === 'refused') {
    return (
      <div className="notice notice-refusal">
        <p className="notice-title">
          <span aria-hidden="true">ⓘ </span>
          <strong>{REFUSAL_TITLE}</strong>
        </p>
        <p>{refusalExplanation(turn.refusalReason)}</p>
      </div>
    );
  }

  const byN = new Map(turn.sources.map((s) => [s.n, s]));
  const toggle = (n, element) => onToggleSource(turn.id, n, element);

  return (
    <div className="answer">
      <p className="answer-text">
        {splitAnswer(turn.answer, turn.sources).map((part, i) =>
          part.type === 'text' ? (
            <span key={i}>{part.value}</span>
          ) : (
            <CitationButton
              key={i}
              className="citation"
              source={byN.get(part.n)}
              expanded={activeN === part.n}
              onToggle={toggle}
            >
              [{part.n}]
            </CitationButton>
          ),
        )}
      </p>
      <h4 className="sources-heading">Sources</h4>
      <ul className="source-list">
        {turn.sources.map((source) => (
          <li key={source.n}>
            <CitationButton
              className="source-link"
              source={source}
              expanded={activeN === source.n}
              onToggle={toggle}
            >
              <span className="source-number">[{source.n}]</span> {source.doc}, page {source.page}
            </CitationButton>
          </li>
        ))}
      </ul>
    </div>
  );
}

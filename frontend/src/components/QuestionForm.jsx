import { useId, useState } from 'react';

const MAX_LENGTH = 1000;

export default function QuestionForm({ onAsk, busy }) {
  const inputId = useId();
  const hintId = useId();
  const [question, setQuestion] = useState('');
  const [error, setError] = useState('');

  function handleSubmit(event) {
    event.preventDefault();
    if (busy) return;
    const trimmed = question.trim();
    if (!trimmed) {
      setError('Type a question first.');
      return;
    }
    setError('');
    setQuestion('');
    onAsk(trimmed);
  }

  return (
    <form className="question-form" onSubmit={handleSubmit} noValidate>
      <label htmlFor={inputId} className="field-label">
        Your question
      </label>
      <div className="question-row">
        <input
          id={inputId}
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          maxLength={MAX_LENGTH}
          autoComplete="off"
          aria-describedby={hintId}
          aria-invalid={error ? true : undefined}
        />
        <button type="submit" className="button" aria-disabled={busy || undefined}>
          {busy ? 'Asking…' : 'Ask'}
        </button>
      </div>
      <p id={hintId} className={error ? 'field-error' : 'hint'}>
        {error ? (
          <>
            <span aria-hidden="true">⚠ </span>
            {error}
          </>
        ) : (
          'Answers come only from your uploaded documents, with numbered sources.'
        )}
      </p>
    </form>
  );
}

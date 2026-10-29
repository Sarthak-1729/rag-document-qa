import Answer from './Answer.jsx';

export default function Conversation({ turns, activeSource, onToggleSource }) {
  if (turns.length === 0) {
    return <p className="hint">Your questions and answers will appear here.</p>;
  }
  return (
    <ol className="conversation" aria-label="Questions and answers">
      {turns.map((turn) => (
        <li key={turn.id}>
          <article className="turn" aria-labelledby={`q-${turn.id}`}>
            <h3 id={`q-${turn.id}`} className="turn-question">
              <span className="visually-hidden">Question: </span>
              {turn.question}
            </h3>
            <Answer
              turn={turn}
              activeN={activeSource?.turnId === turn.id ? activeSource.n : null}
              onToggleSource={onToggleSource}
            />
          </article>
        </li>
      ))}
    </ol>
  );
}

import { useCallback, useEffect, useRef, useState } from 'react';
import Conversation from './components/Conversation.jsx';
import DocumentList from './components/DocumentList.jsx';
import QuestionForm from './components/QuestionForm.jsx';
import SourcePanel from './components/SourcePanel.jsx';
import UploadPanel from './components/UploadPanel.jsx';
import { answerForSpeech } from './lib/citations.js';
import { REFUSAL_TITLE, askErrorMessage } from './lib/messages.js';

let nextTurnId = 1;

// `api` is injected so tests can pass a fake (see src/api/client.js for the real one).
export default function App({ api, confirmDelete = (message) => window.confirm(message) }) {
  const [health, setHealth] = useState(undefined); // undefined = still checking, null = offline
  const [documents, setDocuments] = useState([]);
  const [docsLoading, setDocsLoading] = useState(true);
  const [docsError, setDocsError] = useState('');
  const [deletingId, setDeletingId] = useState(null);
  const [turns, setTurns] = useState([]);
  const [activeSource, setActiveSource] = useState(null); // { turnId, n }
  // Screen-reader announcements. Each gets a fresh id so repeating a message re-announces it.
  const [polite, setPolite] = useState({ id: 0, text: '' });
  const [assertive, setAssertive] = useState({ id: 0, text: '' });

  const documentsHeadingRef = useRef(null);
  const sourceTriggerRef = useRef(null);

  const announce = useCallback((text, { urgent = false } = {}) => {
    const set = urgent ? setAssertive : setPolite;
    set((previous) => ({ id: previous.id + 1, text }));
  }, []);

  const loadDocuments = useCallback(async () => {
    setDocsLoading(true);
    try {
      setDocuments(await api.listDocuments());
      setDocsError('');
    } catch (error) {
      setDocsError(error.detail ?? 'Could not load documents.');
    } finally {
      setDocsLoading(false);
    }
  }, [api]);

  useEffect(() => {
    loadDocuments();
    api.health().then(setHealth, () => setHealth(null));
  }, [api, loadDocuments]);

  function handleUploaded(doc) {
    setDocuments((current) => [...current, doc]);
  }

  async function handleDelete(doc) {
    if (deletingId) return;
    if (!confirmDelete(`Delete "${doc.filename}"? This removes it from search and cannot be undone.`)) {
      return;
    }
    setDeletingId(doc.id);
    try {
      await api.deleteDocument(doc.id);
      setDocuments((current) => current.filter((d) => d.id !== doc.id));
      announce(`Deleted ${doc.filename}.`);
      documentsHeadingRef.current?.focus(); // the focused Delete button no longer exists
    } catch (error) {
      announce(`Could not delete ${doc.filename}: ${error.detail}`, { urgent: true });
    } finally {
      setDeletingId(null);
    }
  }

  const busy = turns.some((t) => t.status === 'pending');

  async function handleAsk(question) {
    const id = nextTurnId++;
    setTurns((current) => [...current, { id, question, status: 'pending' }]);
    announce('Searching your documents…');

    const update = (patch) =>
      setTurns((current) => current.map((t) => (t.id === id ? { ...t, ...patch } : t)));
    try {
      const result = await api.ask(question);
      if (result.refused) {
        update({ status: 'refused', refusalReason: result.refusal_reason });
        announce(REFUSAL_TITLE);
      } else {
        update({ status: 'answered', answer: result.answer, sources: result.sources });
        const count = result.sources.length;
        announce(`Answer: ${answerForSpeech(result.answer)} ${count} source${count === 1 ? '' : 's'}.`);
      }
    } catch (error) {
      const message = askErrorMessage(error);
      update({ status: 'error', error: message });
      announce(''); // clear the stale "Searching…" status
      announce(`Error: ${message.title}. ${message.text}`, { urgent: true });
    }
  }

  function handleToggleSource(turnId, n, trigger) {
    const isOpen = activeSource?.turnId === turnId && activeSource.n === n;
    sourceTriggerRef.current = trigger;
    setActiveSource(isOpen ? null : { turnId, n });
  }

  function handleCloseSource() {
    setActiveSource(null);
    sourceTriggerRef.current?.focus(); // return focus to the citation that opened it
  }

  const source = activeSource
    ? turns.find((t) => t.id === activeSource.turnId)?.sources?.find((s) => s.n === activeSource.n)
    : null;

  return (
    <>
      <a href="#main" className="skip-link">
        Skip to main content
      </a>
      <header className="site-header">
        <h1>Document Q&amp;A</h1>
        <p className="tagline">Answers from your PDFs, with the exact passages they came from.</p>
        <p className="backend-status">
          {health === undefined && 'Checking backend…'}
          {health && (
            <>
              <span aria-hidden="true">● </span>Connected · model: {health.llm_provider}
            </>
          )}
          {health === null && (
            <>
              <span aria-hidden="true">○ </span>Backend not connected
            </>
          )}
        </p>
      </header>

      <main id="main" tabIndex={-1} className="layout">
        <div className="column column-documents">
          <UploadPanel uploadDocument={api.uploadDocument} onUploaded={handleUploaded} />
          <DocumentList
            documents={documents}
            loading={docsLoading}
            error={docsError}
            onDelete={handleDelete}
            deletingId={deletingId}
            headingRef={documentsHeadingRef}
          />
        </div>

        <section className="panel column-chat" aria-labelledby="chat-heading">
          <h2 id="chat-heading">Ask a question</h2>
          <Conversation
            turns={turns}
            activeSource={activeSource}
            onToggleSource={handleToggleSource}
          />
          <QuestionForm onAsk={handleAsk} busy={busy} />
        </section>

        <SourcePanel source={source} onClose={handleCloseSource} />
      </main>

      <div className="visually-hidden" aria-live="polite" aria-atomic="true">
        <span key={polite.id}>{polite.text}</span>
      </div>
      <div className="visually-hidden" aria-live="assertive" aria-atomic="true">
        <span key={assertive.id}>{assertive.text}</span>
      </div>
    </>
  );
}

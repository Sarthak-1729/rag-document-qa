import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import App from './App.jsx';
import {
  ANSWER,
  DOC,
  REFUSAL,
  apiError,
  deferred,
  expectNoAxeViolations,
  fakeApi,
} from './test/helpers.js';

async function setup(overrides = {}, confirmDelete = vi.fn(() => true)) {
  const api = fakeApi(overrides);
  const user = userEvent.setup();
  const view = render(<App api={api} confirmDelete={confirmDelete} />);
  await screen.findByText('nature.pdf'); // initial document list loaded
  const ask = async (question = 'How do volcanoes erupt?') => {
    await user.type(screen.getByLabelText('Your question'), question);
    await user.keyboard('{Enter}');
  };
  const live = (politeness) => view.container.querySelector(`[aria-live="${politeness}"]`);
  // The live regions repeat visible text for screen readers, so query inside the chat log.
  const chat = () => within(screen.getByRole('list', { name: 'Questions and answers' }));
  return { ...view, api, user, ask, live, chat, confirmDelete };
}

describe('App: loading and layout', () => {
  it('shows documents, provider, landmarks and a skip link', async () => {
    const { container } = await setup();
    expect(screen.getByText(/Connected · model: gemini/)).toBeInTheDocument();
    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main');
    expect(screen.getByRole('complementary', { name: 'Source passage' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Skip to main content' })).toHaveAttribute('href', '#main');
    await expectNoAxeViolations(container);
  });

  it('shows an error when documents cannot be loaded and the backend is offline', async () => {
    const api = fakeApi({
      listDocuments: vi.fn().mockRejectedValue(apiError(0, "Can't reach the server.")),
      health: vi.fn().mockRejectedValue(apiError(0)),
    });
    render(<App api={api} />);
    expect(await screen.findByText(/Can't reach the server/)).toBeInTheDocument();
    expect(await screen.findByText('Backend not connected')).toBeInTheDocument();
  });
});

describe('App: asking questions', () => {
  it('shows a loading state, then the answer with numbered citations', async () => {
    const pending = deferred();
    const { ask, live, api, chat } = await setup({ ask: vi.fn(() => pending.promise) });

    await ask();
    expect(api.ask).toHaveBeenCalledWith('How do volcanoes erupt?');
    expect(chat().getByText('Searching your documents…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Asking…' })).toHaveAttribute('aria-disabled', 'true');

    pending.resolve(ANSWER);
    expect(await chat().findByText(/Volcanoes erupt when pressure builds/)).toBeInTheDocument();
    // [1] appears twice inline + once in the sources list; [2] once inline + once in the list.
    expect(screen.getAllByRole('button', { name: 'Source 1: nature.pdf, page 2' })).toHaveLength(3);
    expect(screen.getAllByRole('button', { name: 'Source 2: nature.pdf, page 3' })).toHaveLength(2);
    expect(live('polite')).toHaveTextContent(
      'Answer: Volcanoes erupt when pressure builds. Lava flows down. 2 sources.',
    );
  });

  it('ignores a second submit while a question is pending', async () => {
    const pending = deferred();
    const { ask, api, user, chat } = await setup({ ask: vi.fn(() => pending.promise) });
    await ask('first?');
    await user.type(screen.getByLabelText('Your question'), 'second?{Enter}');
    expect(api.ask).toHaveBeenCalledTimes(1);
    pending.resolve(ANSWER);
    await chat().findByText(/Volcanoes erupt when pressure builds/);
  });

  it('shows a refusal as a labeled non-error state', async () => {
    const { ask, live, chat, container } = await setup({ ask: vi.fn().mockResolvedValue(REFUSAL) });
    await ask('What is the boiling point of mercury?');

    const notice = await chat().findByText("I couldn't find this in your documents");
    expect(notice.closest('.notice')).toHaveClass('notice-refusal');
    expect(screen.queryByText(/^Error:/)).not.toBeInTheDocument();
    expect(live('polite')).toHaveTextContent("I couldn't find this in your documents");
    expect(live('assertive')).toHaveTextContent('');
    await expectNoAxeViolations(container);
  });

  it.each([
    [409, 'Error: No documents yet.', 'Upload at least one PDF'],
    [502, 'Error: The AI model had a problem.', 'server detail'],
    [503, 'Error: AI service unavailable.', 'Try again shortly'],
    [504, 'Error: The AI model took too long.', 'shorter question'],
  ])('shows HTTP %i as an error, not a refusal', async (status, title, text) => {
    const { ask, live } = await setup({ ask: vi.fn().mockRejectedValue(apiError(status)) });
    await ask();

    const error = await screen.findByText(title);
    expect(error.closest('.notice')).toHaveClass('notice-error');
    expect(error.closest('.notice')).toHaveTextContent(text);
    expect(screen.queryByText("I couldn't find this in your documents")).not.toBeInTheDocument();
    expect(live('assertive')).toHaveTextContent(title.replace('Error: ', ''));
  });

  it('shows the Retry-After seconds on 429', async () => {
    const { ask, live, chat } = await setup({
      ask: vi.fn().mockRejectedValue(apiError(429, 'Too many questions.', 12)),
    });
    await ask();
    expect(await chat().findByText(/Please wait 12 seconds and try again/)).toBeInTheDocument();
    expect(live('assertive')).toHaveTextContent('Please wait 12 seconds');
    expect(live('polite')).toHaveTextContent(''); // stale "Searching…" was cleared
  });

  it('asks for text before submitting an empty question', async () => {
    const { user, api } = await setup();
    await user.click(screen.getByRole('button', { name: 'Ask' }));
    expect(screen.getByText('Type a question first.')).toBeInTheDocument();
    expect(screen.getByLabelText('Your question')).toHaveAttribute('aria-invalid', 'true');
    expect(api.ask).not.toHaveBeenCalled();
  });
});

describe('App: citations and the source panel', () => {
  it('opens the source panel with aria-expanded, and returns focus on close', async () => {
    const { ask, user, container } = await setup();
    await ask();
    const [citation] = await screen.findAllByRole('button', { name: 'Source 2: nature.pdf, page 3' });
    expect(citation).toHaveAttribute('aria-expanded', 'false');
    expect(citation).toHaveAttribute('aria-controls', 'source-panel');

    await user.click(citation);
    expect(citation).toHaveAttribute('aria-expanded', 'true');
    const panel = screen.getByRole('complementary', { name: 'Source passage' });
    expect(within(panel).getByText('nature.pdf')).toBeInTheDocument();
    expect(within(panel).getByText('3')).toBeInTheDocument(); // PDF page
    expect(within(panel).getByText('Lava flows down its slopes.')).toBeInTheDocument();
    await expectNoAxeViolations(container);

    await user.click(within(panel).getByRole('button', { name: 'Close source' }));
    expect(citation).toHaveAttribute('aria-expanded', 'false');
    expect(citation).toHaveFocus();
    expect(within(panel).getByText(/Select a citation/)).toBeInTheDocument();
  });

  it('works with the keyboard and toggles closed on a second press', async () => {
    const { ask, user } = await setup();
    await ask();
    const [citation] = await screen.findAllByRole('button', { name: 'Source 1: nature.pdf, page 2' });

    citation.focus();
    await user.keyboard('{Enter}');
    expect(citation).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Magma rises through cracks.')).toBeInTheDocument();

    await user.keyboard(' '); // Space also activates buttons
    expect(citation).toHaveAttribute('aria-expanded', 'false');
  });
});

describe('App: deleting documents', () => {
  it('does nothing when the user cancels the confirmation', async () => {
    const confirmDelete = vi.fn(() => false);
    const { user, api } = await setup({}, confirmDelete);
    await user.click(screen.getByRole('button', { name: 'Delete nature.pdf' }));
    expect(confirmDelete).toHaveBeenCalledWith(expect.stringContaining('nature.pdf'));
    expect(api.deleteDocument).not.toHaveBeenCalled();
    expect(screen.getByText('nature.pdf')).toBeInTheDocument();
  });

  it('deletes after confirmation, announces it and moves focus to the list heading', async () => {
    const { user, api, live } = await setup();
    await user.click(screen.getByRole('button', { name: 'Delete nature.pdf' }));

    await waitFor(() => expect(api.deleteDocument).toHaveBeenCalledWith(DOC.id));
    await waitFor(() => expect(screen.queryByText('nature.pdf')).not.toBeInTheDocument());
    expect(screen.getByRole('heading', { name: 'Your documents' })).toHaveFocus();
    expect(live('polite')).toHaveTextContent('Deleted nature.pdf.');
  });

  it('keeps the document and announces an error when delete fails', async () => {
    const { user, live } = await setup({
      deleteDocument: vi.fn().mockRejectedValue(apiError(500, 'disk error')),
    });
    await user.click(screen.getByRole('button', { name: 'Delete nature.pdf' }));
    await waitFor(() => expect(live('assertive')).toHaveTextContent('Could not delete nature.pdf: disk error'));
    expect(screen.getByText('nature.pdf')).toBeInTheDocument();
  });
});

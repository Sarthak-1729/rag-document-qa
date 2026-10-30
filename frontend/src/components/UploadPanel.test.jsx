import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { DOC, apiError, deferred, expectNoAxeViolations, pdfFile } from '../test/helpers.js';
import UploadPanel from './UploadPanel.jsx';

function setup(uploadDocument) {
  const onUploaded = vi.fn();
  const user = userEvent.setup({ applyAccept: false });
  const view = render(<UploadPanel uploadDocument={uploadDocument} onUploaded={onUploaded} />);
  const input = screen.getByLabelText('Choose PDF files');
  const submit = () => user.click(screen.getByRole('button', { name: /upload/i }));
  return { ...view, user, input, submit, onUploaded };
}

const rows = () => within(screen.getByRole('list', { name: 'Upload results' })).getAllByRole('listitem');

describe('UploadPanel', () => {
  it('shows a progress bar while uploading, then success', async () => {
    const pending = deferred();
    const upload = vi.fn((file, onProgress) => {
      onProgress(40);
      return pending.promise;
    });
    const { user, input, submit, onUploaded } = setup(upload);

    await user.upload(input, pdfFile());
    await submit();

    const bar = screen.getByRole('progressbar', { name: 'Uploading nature.pdf' });
    expect(bar).toHaveAttribute('value', '40');
    expect(screen.getByRole('button', { name: 'Uploading…' })).toHaveAttribute('aria-disabled', 'true');

    pending.resolve(DOC);
    expect(await screen.findByText(/Added \(3 pages\)/)).toBeInTheDocument();
    expect(onUploaded).toHaveBeenCalledWith(DOC);
    expect(screen.getByRole('status')).toHaveTextContent('Upload finished: 1 added.');
  });

  it.each([
    [409, 'Error: Already uploaded.'],
    [413, 'Error: File too large.'],
    [422, "Error: Couldn't read this PDF."],
  ])('shows a clear error row for HTTP %i', async (status, text) => {
    const upload = vi.fn().mockRejectedValue(apiError(status, 'detail from server'));
    const { user, input, submit, onUploaded } = setup(upload);

    await user.upload(input, pdfFile());
    await submit();

    const [row] = rows();
    expect(await within(row).findByText(text)).toBeInTheDocument();
    expect(row).toHaveTextContent('detail from server');
    expect(onUploaded).not.toHaveBeenCalled();
  });

  it('uploads files one by one so one failure does not block the rest', async () => {
    const upload = vi
      .fn()
      .mockRejectedValueOnce(apiError(409, 'dup'))
      .mockResolvedValueOnce({ ...DOC, filename: 'b.pdf' });
    const { user, input, submit } = setup(upload);

    await user.upload(input, [pdfFile('a.pdf'), pdfFile('b.pdf')]);
    await submit();

    expect(await screen.findByText('Upload finished: 1 added, 1 failed (details below).')).toBeInTheDocument();
    const [first, second] = rows();
    expect(first).toHaveTextContent('Already uploaded');
    expect(second).toHaveTextContent('Added');
  });

  it('rejects non-PDF files before uploading them', async () => {
    const upload = vi.fn();
    const { user, input, submit } = setup(upload);

    await user.upload(input, new File(['x'], 'notes.txt', { type: 'text/plain' }));
    await submit();

    expect(await screen.findByText('Error: Not a PDF.')).toBeInTheDocument();
    expect(upload).not.toHaveBeenCalled();
  });

  it('asks the user to choose a file when none is selected', async () => {
    const { submit, input } = setup(vi.fn());
    await submit();
    expect(screen.getByRole('status')).toHaveTextContent('Choose at least one PDF file first.');
    expect(input).toHaveFocus();
  });

  it('has no axe violations with error and success rows', async () => {
    const upload = vi.fn().mockRejectedValueOnce(apiError(413, 'big')).mockResolvedValueOnce(DOC);
    const { user, input, submit, container } = setup(upload);
    await user.upload(input, [pdfFile('a.pdf'), pdfFile('b.pdf')]);
    await submit();
    await screen.findByText(/Upload finished/);
    await expectNoAxeViolations(container);
  });
});

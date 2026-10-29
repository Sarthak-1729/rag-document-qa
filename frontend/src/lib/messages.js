// Turn API errors and refusal reasons into short, human messages.
// Each message has a title (what happened) and text (what to do / server detail).

export function uploadErrorMessage(error) {
  const detail = error?.detail ?? '';
  switch (error?.status) {
    case 0:
      return { title: 'Server unreachable', text: `${detail} Is the backend running?` };
    case 409:
      return { title: 'Already uploaded', text: detail };
    case 413:
      return { title: 'File too large', text: detail };
    case 415:
      return { title: 'Not a PDF', text: `${detail} Only .pdf files can be uploaded.` };
    case 422:
      return {
        title: "Couldn't read this PDF",
        text: `${detail} Scanned or password-protected PDFs aren't supported.`,
      };
    default:
      return { title: 'Upload failed', text: detail || 'Something went wrong. Please try again.' };
  }
}

export function askErrorMessage(error) {
  const detail = error?.detail ?? '';
  switch (error?.status) {
    case 0:
      return { title: 'Server unreachable', text: `${detail} Is the backend running?` };
    case 409:
      return { title: 'No documents yet', text: 'Upload at least one PDF, then ask your question.' };
    case 422:
      return { title: 'Check your question', text: detail };
    case 429: {
      const wait = error.retryAfter
        ? `Please wait ${error.retryAfter} second${error.retryAfter === 1 ? '' : 's'}`
        : 'Please wait a moment';
      return { title: 'Too many questions', text: `${wait} and try again.` };
    }
    case 502:
      return { title: 'The AI model had a problem', text: detail };
    case 503:
      return { title: 'AI service unavailable', text: `${detail} Try again shortly.` };
    case 504:
      return { title: 'The AI model took too long', text: 'Try again, or ask a shorter question.' };
    default:
      return { title: 'Something went wrong', text: detail || 'Please try again.' };
  }
}

export const REFUSAL_TITLE = "I couldn't find this in your documents";

export function refusalExplanation(reason) {
  switch (reason) {
    case 'low_relevance':
      return 'None of the uploaded documents seem related to this question.';
    case 'uncited':
      return "The model's answer couldn't be linked to a source passage, so it isn't shown.";
    default:
      return "The relevant passages don't contain an answer to this question.";
  }
}

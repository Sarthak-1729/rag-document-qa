// Split an answer like "Plants make sugar [1] using light [2]." into text and citation parts.
// Only markers that match a returned source become citations; anything else stays text.

const MARKER = /\[(\d+)\]/g;

export function splitAnswer(answer, sources) {
  const known = new Set(sources.map((s) => s.n));
  const parts = [];
  let last = 0;
  for (const match of answer.matchAll(MARKER)) {
    const n = Number(match[1]);
    if (!known.has(n)) continue;
    if (match.index > last) parts.push({ type: 'text', value: answer.slice(last, match.index) });
    parts.push({ type: 'citation', n });
    last = match.index + match[0].length;
  }
  if (last < answer.length) parts.push({ type: 'text', value: answer.slice(last) });
  return parts;
}

// Plain-text version for screen-reader announcements: "[1]" reads poorly, so drop markers.
export function answerForSpeech(answer) {
  return answer.replace(MARKER, '').replace(/\s+([.,;:])/g, '$1').trim();
}

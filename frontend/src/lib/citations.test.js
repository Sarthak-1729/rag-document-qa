import { describe, expect, it } from 'vitest';
import { answerForSpeech, splitAnswer } from './citations.js';

const sources = [{ n: 1 }, { n: 2 }];

describe('splitAnswer', () => {
  it('splits text and known citations in order', () => {
    expect(splitAnswer('A [1] and B [2].', sources)).toEqual([
      { type: 'text', value: 'A ' },
      { type: 'citation', n: 1 },
      { type: 'text', value: ' and B ' },
      { type: 'citation', n: 2 },
      { type: 'text', value: '.' },
    ]);
  });

  it('keeps adjacent and repeated citations', () => {
    expect(splitAnswer('X [1][2][1]', sources)).toEqual([
      { type: 'text', value: 'X ' },
      { type: 'citation', n: 1 },
      { type: 'citation', n: 2 },
      { type: 'citation', n: 1 },
    ]);
  });

  it('leaves markers without a matching source as plain text', () => {
    expect(splitAnswer('Year [1788] and [9] here [1]', sources)).toEqual([
      { type: 'text', value: 'Year [1788] and [9] here ' },
      { type: 'citation', n: 1 },
    ]);
  });

  it('handles answers with no citations or empty text', () => {
    expect(splitAnswer('plain', sources)).toEqual([{ type: 'text', value: 'plain' }]);
    expect(splitAnswer('', sources)).toEqual([]);
  });
});

describe('answerForSpeech', () => {
  it('drops markers and the space before punctuation', () => {
    expect(answerForSpeech('Lava flows [1][2]. It cools [3], then stops.')).toBe(
      'Lava flows. It cools, then stops.',
    );
  });
});

// Splits a sentence/paragraph into a short bold "lede" plus the rest, for
// skimmable bulleted fact lists (e.g. Bird Profile's Cool Facts, sourced
// live from All About Birds — arbitrary, per-species, non-hardcodable
// text, so this can't be a lookup table; it has to work on any real
// sentence shape).
//
// Picks the most natural break point available, in priority order:
//   1. A real sentence end (. ! ?) if the resulting lede is a sensible
//      length (not a one-word "fact." nor a run-on paragraph).
//   2. A comma inside the target word window — skipped if the comma
//      sits inside a number ("9 years, 2 months") rather than between
//      clauses, checked by requiring a letter (not a digit) right after
//      the comma+space.
//   3. A plain word-count cutoff at MIN_WORDS+3, as a fallback that
//      still lands on a real word boundary.
//
// Whichever of the above is picked, the result is then checked against
// STOP_ENDINGS (below) and extended forward if it would otherwise end on
// a dangling preposition/conjunction/article ("...drum loudly against",
// "...was a male and") — a real, reported bug: those read like the
// sentence was cut off mid-thought rather than genuinely summarized.
// Extension walks forward to the next real clause break (a non-numeric
// comma or sentence end) rather than an arbitrary word count, since that
// consistently produces a complete-sounding phrase regardless of how far
// away the break naturally falls.

const MIN_WORDS = 6
const MAX_WORDS = 14
const MAX_EXTENSION_WORDS = 20 // hard cap so a pathological fact can't bold the whole paragraph

// Words that shouldn't be the last word of a bolded lede — each of these
// grammatically demands something after it, so ending there reads as an
// abrupt cutoff rather than a real clause boundary.
const STOP_ENDINGS = new Set([
  'a', 'an', 'the',
  'and', 'or', 'but', 'nor', 'so', 'yet',
  'to', 'of', 'in', 'on', 'at', 'by', 'for', 'with', 'from',
  'into', 'onto', 'upon', 'over', 'under', 'through', 'during',
  'about', 'before', 'after', 'between', 'among', 'against',
  'as', 'than', 'that', 'which', 'who', 'whom', 'whose',
  'if', 'because', 'while', 'when', 'where',
  'is', 'was', 'are', 'were', 'be', 'been', 'being',
  'has', 'have', 'had', 'not', 'no',
  'least', 'most', // "at least 9 years" / "at most" — near-universal in these facts' longevity records
])

function lastWordOf(str) {
  const words = str.trim().split(/\s+/)
  return (words[words.length - 1] || '').toLowerCase().replace(/[^a-z']/g, '')
}

// Extends a candidate cut forward (never backward — never shortens a
// cut that already reads fine) until it lands on a real clause break: a
// comma not sitting inside a number, or sentence-ending punctuation.
// Falls back to just walking past the dangling word(s) if neither shows
// up before the hard cap.
function extendPastDanglingWord(text, cutLength) {
  const commaRe = /,(?=\s+[A-Za-z])/g
  const sentenceRe = /[.!?](?=\s|$)/g

  commaRe.lastIndex = cutLength
  const commaMatch = commaRe.exec(text)
  const commaAt = commaMatch ? commaMatch.index + 1 : Infinity

  sentenceRe.lastIndex = cutLength
  const sentenceMatch = sentenceRe.exec(text)
  const sentenceAt = sentenceMatch ? sentenceMatch.index + 1 : Infinity

  const bestIndex = Math.min(commaAt, sentenceAt)
  const wordsAtBest = bestIndex === Infinity ? Infinity : text.slice(0, bestIndex).trim().split(/\s+/).length

  if (bestIndex !== Infinity && wordsAtBest <= MAX_EXTENSION_WORDS) {
    return text.slice(0, bestIndex).trim()
  }

  // No real clause break within range — walk forward one word at a time
  // past the dangling word(s) until landing on something that isn't
  // itself a dangling word, capped at MAX_EXTENSION_WORDS total.
  const words = text.trim().split(/\s+/)
  let count = text.slice(0, cutLength).trim().split(/\s+/).length
  while (count < words.length && count < MAX_EXTENSION_WORDS) {
    count++
    const candidate = words.slice(0, count).join(' ')
    if (!STOP_ENDINGS.has(lastWordOf(candidate))) {
      return candidate
    }
  }
  return words.slice(0, Math.min(count, words.length)).join(' ')
}

export function splitLede(text) {
  if (!text) return ['', '']
  const words = text.trim().split(/\s+/)

  let bold = null

  const sentenceMatch = text.match(/^.*?[.!?](?=\s|$)/)
  if (sentenceMatch) {
    const wc = sentenceMatch[0].split(/\s+/).length
    if (wc >= MIN_WORDS && wc <= MAX_WORDS + 4) {
      bold = sentenceMatch[0].trim()
    }
  }

  if (bold === null) {
    const commaRe = /,(?=\s+[A-Za-z])/g
    let m
    while ((m = commaRe.exec(text))) {
      const wc = text.slice(0, m.index + 1).split(/\s+/).length
      if (wc >= MIN_WORDS && wc <= MAX_WORDS) {
        bold = text.slice(0, m.index + 1).trim()
        break
      }
      if (wc > MAX_WORDS) break
    }
  }

  if (bold === null) {
    bold = words.slice(0, MIN_WORDS + 3).join(' ')
  }

  if (STOP_ENDINGS.has(lastWordOf(bold))) {
    bold = extendPastDanglingWord(text, bold.length)
  }

  return [bold, text.slice(bold.length).trim()]
}

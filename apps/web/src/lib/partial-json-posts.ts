/**
 * Streaming JSON-mode response'tan posts[N].text field'larını partial olarak
 * çıkarır (#538).
 *
 * Backend `event: chunk` ile her DeepSeek delta'sını yolluyor; useGenerationStream
 * bunu `rawAccumulator`'a biriktiriyor. Bu helper accumulator buffer'ından
 * o ana kadar gelen post.text'lerini parse edip kullanıcıya canlı gösterir.
 *
 * Şema (content_generator.SYSTEM_PROMPT_X_POST):
 *   {
 *     "posts": [
 *       {"text": "...", "angle": "...", "char_count": N, "related_agenda_card_ids": [...]},
 *       ...
 *     ],
 *     "summary": "...",
 *     ...
 *   }
 *
 * "text" her zaman post objesinin İLK field'ı; pattern `\{\s*"text"\s*:\s*"...`.
 */

export interface PartialPost {
  index: number;
  partialText: string;
  /** True ise text string kapanmış (`"` görüldü) — post tamamlanmaya yakın. */
  textClosed: boolean;
}

// Regex pattern'leri arrayKey/fieldKey'ler için cache'lenmiş factory.
// `\{\s*"<field>"\s*:\s*"...` — schema garantisi: field her zaman objenin İLK
// alanı (content_generator: posts[].text, summary_doc_items[].event, ...).
const _arrayReCache = new Map<string, RegExp>();
const _closedFieldReCache = new Map<string, RegExp>();
const _openFieldReCache = new Map<string, RegExp>();

function _arrayRe(arrayKey: string): RegExp {
  let re = _arrayReCache.get(arrayKey);
  if (!re) {
    re = new RegExp(`"${arrayKey}"\\s*:\\s*\\[`);
    _arrayReCache.set(arrayKey, re);
  }
  return re;
}

function _closedFieldRe(fieldKey: string): RegExp {
  let re = _closedFieldReCache.get(fieldKey);
  if (!re) {
    re = new RegExp(
      `\\{\\s*"${fieldKey}"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)"(?=\\s*[,}]|$)`,
      "g",
    );
    _closedFieldReCache.set(fieldKey, re);
  }
  // Reset state for re-use (g flag has stateful lastIndex)
  re.lastIndex = 0;
  return re;
}

function _openFieldRe(fieldKey: string): RegExp {
  let re = _openFieldReCache.get(fieldKey);
  if (!re) {
    re = new RegExp(
      `\\{\\s*"${fieldKey}"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)\\\\?$`,
    );
    _openFieldReCache.set(fieldKey, re);
  }
  return re;
}

/**
 * Genel partial extractor — buffer'da `<arrayKey>: [{<fieldKey>: "..."}, ...]`
 * pattern'inden her item'in partial decoded text'ini çıkarır.
 *
 * Schema sözleşmesi: extracted field her zaman objenin İLK alanı olmalı
 * (content_generator output'unda doğru: posts[].text, summary_doc_items[].event).
 */
export function extractPartialFieldArray(
  buffer: string,
  arrayKey: string,
  fieldKey: string,
): PartialPost[] {
  const arrayRe = _arrayRe(arrayKey);
  const arrayMatch = arrayRe.exec(buffer);
  if (!arrayMatch) return [];

  const sub = buffer.slice(arrayMatch.index + arrayMatch[0].length);
  const out: PartialPost[] = [];

  const closedRe = _closedFieldRe(fieldKey);
  let m: RegExpExecArray | null;
  let itemIndex = 0;
  let lastClosedEnd = 0;
  while ((m = closedRe.exec(sub)) !== null) {
    out.push({
      index: itemIndex,
      partialText: jsonUnescapePartial(m[1]),
      textClosed: true,
    });
    itemIndex++;
    lastClosedEnd = m.index + m[0].length;
    if (m.index === closedRe.lastIndex) {
      closedRe.lastIndex++;
    }
  }

  const remaining = sub.slice(lastClosedEnd);
  const openMatch = _openFieldRe(fieldKey).exec(remaining);
  if (openMatch) {
    out.push({
      index: itemIndex,
      partialText: jsonUnescapePartial(openMatch[1]),
      textClosed: false,
    });
  }

  return out;
}

/**
 * Buffer'da `posts[]` array'inin partial post.text'lerini çıkarır.
 * (extractPartialFieldArray üzerinden ince wrapper — backward-compat.)
 */
export function extractPartialPostTexts(buffer: string): PartialPost[] {
  return extractPartialFieldArray(buffer, "posts", "text");
}

/**
 * Buffer'da `summary_doc.items[]` (NESTED) array'inin partial event metinlerini
 * çıkarır. Backend content_generator SUMMARY prompt'u nested şema kullanıyor:
 *
 *   {"summary_doc": {"title": "...", "items": [{"event": "..."}, ...]}, ...}
 *
 * (#545 → #550 — flat path yerine nested doğru path.)
 */
export function extractPartialSummaryItems(buffer: string): PartialPost[] {
  // Önce parent obj scope'unu bul
  const parentMatch = /"summary_doc"\s*:\s*\{/.exec(buffer);
  if (!parentMatch) return [];
  const sub = buffer.slice(parentMatch.index + parentMatch[0].length);
  return extractPartialFieldArray(sub, "items", "event");
}

/**
 * Buffer'da `summary_doc.title` (NESTED) scalar string'inin partial decoded
 * metnini döner.
 */
export function extractPartialSummaryTitle(
  buffer: string,
): { text: string; closed: boolean } | null {
  const parentMatch = /"summary_doc"\s*:\s*\{/.exec(buffer);
  if (!parentMatch) return null;
  const sub = buffer.slice(parentMatch.index + parentMatch[0].length);
  return extractPartialScalarString(sub, "title");
}

/**
 * Top-level scalar string field'ının partial decoded text'ini döner.
 * Örn: `summary_doc_title`. Bulunamazsa null.
 *
 * Pattern: `"<key>"\s*:\s*"<captured>("?)` — closing quote varsa kapanmış.
 */
export function extractPartialScalarString(
  buffer: string,
  key: string,
): { text: string; closed: boolean } | null {
  const re = new RegExp(
    `"${key}"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)("?)(?=\\s*[,}]|$)`,
  );
  const m = re.exec(buffer);
  if (!m) {
    // Fallback: open string (no closing quote, end of buffer)
    const openRe = new RegExp(
      `"${key}"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)\\\\?$`,
    );
    const om = openRe.exec(buffer);
    if (!om) return null;
    return { text: jsonUnescapePartial(om[1]), closed: false };
  }
  return {
    text: jsonUnescapePartial(m[1]),
    closed: m[2] === '"',
  };
}

/**
 * JSON escape sequence'ları decode eder. Yarım kalmış escape (trailing `\`,
 * partial `\uXX..`) varsa atlar — sonraki feed tamamlayacak.
 */
export function jsonUnescapePartial(s: string): string {
  const out: string[] = [];
  let i = 0;
  const n = s.length;
  while (i < n) {
    const c = s[i];
    if (c !== "\\") {
      out.push(c);
      i++;
      continue;
    }
    if (i + 1 >= n) {
      // Trailing `\` — partial, drop
      break;
    }
    const next = s[i + 1];
    switch (next) {
      case "n":
        out.push("\n");
        i += 2;
        break;
      case "t":
        out.push("\t");
        i += 2;
        break;
      case "r":
        out.push("\r");
        i += 2;
        break;
      case "b":
        out.push("\b");
        i += 2;
        break;
      case "f":
        out.push("\f");
        i += 2;
        break;
      case '"':
        out.push('"');
        i += 2;
        break;
      case "\\":
        out.push("\\");
        i += 2;
        break;
      case "/":
        out.push("/");
        i += 2;
        break;
      case "u": {
        if (i + 6 > n) {
          return out.join("");
        }
        const hex = s.slice(i + 2, i + 6);
        if (!/^[0-9a-fA-F]{4}$/.test(hex)) {
          out.push("\\u");
          i += 2;
        } else {
          out.push(String.fromCharCode(parseInt(hex, 16)));
          i += 6;
        }
        break;
      }
      default:
        out.push(next);
        i += 2;
        break;
    }
  }
  return out.join("");
}

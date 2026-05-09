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

const POSTS_ARRAY_RE = /"posts"\s*:\s*\[/;

// Closed text: { "text": "..." } — followed by `,` or `}` (next field/end of
// object) VEYA buffer end-of-string (just-closed, virgül henüz gelmemiş).
const POST_TEXT_CLOSED_RE =
  /\{\s*"text"\s*:\s*"((?:\\.|[^"\\])*)"(?=\s*[,}]|$)/g;

// Open text at end-of-buffer (still streaming). `\\?$` ile trailing partial
// backslash'i (örn. `"Foo \`) capture dışında kalmasına izin ver — escape
// yarım kalmış.
const POST_TEXT_OPEN_RE = /\{\s*"text"\s*:\s*"((?:\\.|[^"\\])*)\\?$/;

/**
 * Buffer'da `posts[]` array'ini bulup her post.text alanının partial decode'unu
 * döner. Closed text'ler valid JSON string'lerdir; en sondaki open text aktif
 * yazılıyor olabilir.
 */
export function extractPartialPostTexts(buffer: string): PartialPost[] {
  const arrayMatch = POSTS_ARRAY_RE.exec(buffer);
  if (!arrayMatch) return [];

  const sub = buffer.slice(arrayMatch.index + arrayMatch[0].length);
  const out: PartialPost[] = [];

  // 1. Closed text fields — valid JSON, we know exactly where they end
  POST_TEXT_CLOSED_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  let postIndex = 0;
  let lastClosedEnd = 0;
  while ((m = POST_TEXT_CLOSED_RE.exec(sub)) !== null) {
    out.push({
      index: postIndex,
      partialText: jsonUnescapePartial(m[1]),
      textClosed: true,
    });
    postIndex++;
    lastClosedEnd = m.index + m[0].length;
    // Avoid infinite loops on zero-length matches
    if (m.index === POST_TEXT_CLOSED_RE.lastIndex) {
      POST_TEXT_CLOSED_RE.lastIndex++;
    }
  }

  // 2. Open text — only at very end of buffer (still streaming)
  const remaining = sub.slice(lastClosedEnd);
  const openMatch = POST_TEXT_OPEN_RE.exec(remaining);
  if (openMatch) {
    out.push({
      index: postIndex,
      partialText: jsonUnescapePartial(openMatch[1]),
      textClosed: false,
    });
  }

  return out;
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

"""Streaming JSON post extractor (issue #527).

Content Generator JSON-mode response chunk-by-chunk gelir:
    {"posts": [{"text": "...", "angle": "...", "char_count": N,
                "related_agenda_card_ids": [...]}, ...],
     "summary": "...", ...}

Bu modül accumulating buffer'dan TAMAMLANMIŞ `posts[i]` objelerini erkenden
parse edip emit etmeye yarar. Backend her chunk geldiğinde `feed(chunk)`
çağırır; tamamlanmış post varsa döner.

Yaklaşım:
- Buffer'da `"posts": [` pattern'ini bul (bir kere).
- Bu noktadan sonra brace-balance ile her tam `{...}` objesi tespit et;
  string içindeyken `}` saymayan minimal state machine.
- Tespit edilen objeyi `json.loads` ile parse et.
- Daha önce emit edilenleri tekrar etmemek için son emit edilen pozisyonu
  takip et.

Hata toleranslı: malformed string/escape varsa o post'u skip; final full
parse caller tarafında zaten yapılır (parse_x_post_response).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# `"posts"` veya `'posts'` (defensive) ardından `:` ardından `[` arar
_POSTS_ARRAY_RE = re.compile(r'"posts"\s*:\s*\[')


@dataclass
class StreamingPostExtractor:
    """Stateful incremental post extractor."""

    buffer: list[str] = field(default_factory=list)
    """Tüm chunk'ların concat birikimi (list-join performance)."""

    posts_array_start: int = -1
    """Buffer'da `"posts": [` sonrasının başlangıç pozisyonu (-1: henüz bulunmadı)."""

    scan_pos: int = 0
    """Bir sonraki tarama başlayacağı pozisyon (posts array içinde)."""

    emitted_count: int = 0
    """Şu ana kadar emit edilen post sayısı (caller'a index olarak geçer)."""

    posts_array_closed: bool = False
    """`]` ile posts array'i kapandıysa True (artık daha fazla post aranmaz)."""

    def feed(self, chunk: str) -> list[tuple[int, dict]]:
        """Buffer'a chunk ekle; bu feed sonrası tespit edilen yeni post'ları döner.

        Returns: list[(post_index, post_dict)]
        """
        if not chunk:
            return []
        self.buffer.append(chunk)
        return self._scan()

    def buffer_text(self) -> str:
        return "".join(self.buffer)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _scan(self) -> list[tuple[int, dict]]:
        if self.posts_array_closed:
            return []

        text = self.buffer_text()

        # Step 1: `"posts": [` aranır (yalnızca bir kere)
        if self.posts_array_start < 0:
            m = _POSTS_ARRAY_RE.search(text)
            if not m:
                return []
            self.posts_array_start = m.end()
            self.scan_pos = m.end()

        results: list[tuple[int, dict]] = []

        # Step 2: scan_pos'tan itibaren her bir tam `{...}` post'u bul
        pos = self.scan_pos
        n = len(text)

        while pos < n:
            # Whitespace + comma skip
            ch = text[pos]
            if ch in " \t\n\r,":
                pos += 1
                continue
            # Posts array kapandı mı?
            if ch == "]":
                self.posts_array_closed = True
                self.scan_pos = pos + 1
                break
            if ch != "{":
                # Beklenmedik karakter — chunk yarım gelmiş olabilir, bekle
                self.scan_pos = pos
                break

            # `{` bulundu — matching `}` ara (string-aware)
            end = self._find_matching_brace(text, pos)
            if end < 0:
                # Henüz tamamlanmadı — sonraki chunk'ı bekle
                self.scan_pos = pos
                break

            # `text[pos:end+1]` tam JSON objesi
            obj_str = text[pos : end + 1]
            try:
                obj = json.loads(obj_str)
            except ValueError:
                # Bozuk JSON — bu objeyi atla, sonrakine geç
                pos = end + 1
                continue

            if isinstance(obj, dict):
                results.append((self.emitted_count, obj))
                self.emitted_count += 1

            pos = end + 1
            self.scan_pos = pos

        return results

    @staticmethod
    def _find_matching_brace(text: str, start: int) -> int:
        """text[start] == '{' varsayar; eşleşen '}' indeksini döner.

        String içinde olan `{`/`}` saymaz. Buffer yetersizse -1 döner.
        """
        if start >= len(text) or text[start] != "{":
            return -1
        depth = 0
        i = start
        n = len(text)
        in_string = False
        escape = False
        while i < n:
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return i
            i += 1
        return -1

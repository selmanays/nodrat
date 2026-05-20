"""Text similarity metrics — Levenshtein normalize utility.

User'ın LLM çıktısını ne kadar düzenlediğini ölçmek için kullanılır.
Düzenleme distance'ı SFT eligibility kuralının bir parametresi
(generations.edit_distance, #563).

İçerik tipi: tek-dosya pure-python implementation. Harici dependency
istemez (production'da `Levenshtein` C-extension daha hızlı olabilir
ama deploy/build complexity için pure-python yeterli — generation
metni tipik <2K char, ms mertebesinde).

Kullanım:
    from app.modules.style_profiles.text_metrics import normalized_levenshtein_distance

    distance = normalized_levenshtein_distance(original, edited)
    # 0.0 = identik, 1.0 = tamamen farklı

Refs: #566
"""

from __future__ import annotations


def levenshtein_distance(s1: str, s2: str) -> int:
    """Iterative Wagner-Fischer matrix dynamic programming.

    Time:  O(len(s1) * len(s2))
    Space: O(min(len(s1), len(s2)))  — single-row optimization
    """
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)

    if len(s1) > len(s2):
        s1, s2 = s2, s1

    previous_row = list(range(len(s1) + 1))
    for i, c2 in enumerate(s2, start=1):
        current_row = [i]
        for j, c1 in enumerate(s1, start=1):
            insertions = previous_row[j] + 1
            deletions = current_row[j - 1] + 1
            substitutions = previous_row[j - 1] + (0 if c1 == c2 else 1)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def normalized_levenshtein_distance(s1: str, s2: str) -> float:
    """0.0 = identik, 1.0 = tamamen farklı.

    Formula: levenshtein(s1, s2) / max(len(s1), len(s2))

    Both empty strings → 0.0 (definition: identik).
    One empty → 1.0 (definition: tamamen farklı).

    NOT NUMERIC(4,3) için DB'ye yazılmadan önce round(value, 3) yap.
    """
    if not s1 and not s2:
        return 0.0
    longer_len = max(len(s1), len(s2))
    if longer_len == 0:  # safety, normalde yukarıdan yakalanır
        return 0.0
    return levenshtein_distance(s1, s2) / longer_len

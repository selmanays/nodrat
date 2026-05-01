---
description: Nodrat test workflow — unit / integration / E2E / LLM eval testleri + kalite eşikleri (halü <%2, citation %100)
---

# /nodrat-test — Test ve Kalite Kontrol

Bu komut, test türünü tespit eder, ilgili testleri koşar ve sonuçları raporlar.

---

## 1. Test Türleri

### Unit
```bash
pytest tests/unit/ -v
pytest --cov=apps/api --cov-report=term-missing
cd apps/web && npm test
```
Hedef: ≥%70 coverage, kritik path ≥%85, <30s.

### Integration
```bash
docker compose -f docker-compose.test.yml up -d
pytest tests/integration/ -v
docker compose -f docker-compose.test.yml down
```
DB migration, API+DB, worker+queue, provider mock, auth flow.

### E2E
```bash
npx playwright test
npx playwright test tests/e2e/aha-moment.spec.ts
```
Senaryolar: register→verify→first generation→save, login, admin source ekleme, insufficient data.

### LLM Eval
```bash
pytest tests/eval/test_query_planner.py
pytest tests/eval/test_agenda_card.py
pytest tests/eval/test_content_generator.py
pytest tests/eval/test_hallucination.py
```

---

## 2. Kalite Eşikleri (Quality Gates)

### Otomatik (CI'da merge engelleyici)
```text
Test coverage           : ≥%70 (kritik ≥%85)
Lint pass               : 100%
Type check              : 100%
Unit / Integration test : 100%
```

### LLM kalite
```text
Hallucination rate           : <%2
Generation success rate      : >%95
Source citation rate         : 100%
Schema validation pass       : ≥%99
Direct quote 25-word cap     : 100%
INSUFFICIENT_DATA accuracy   : >%90
PII redaction effectiveness  : ≥%99
Sensitive entity attribution : 100%
```

### UX/UI
```text
Latency p95          : Generate <8s, Page load <2s
WCAG AA              : 100% (Faz 6 öncesi audit)
Browser              : Chrome/Safari/Firefox son 2 sürüm
Mobile responsive    : Tablet+
```

---

## 3. Akış

### Local geliştirme
```bash
pytest tests/unit/test_<changed_module>.py -v
ruff check . && black --check . && mypy apps/api
cd apps/web && npm run lint && npm run type-check && npm test
```

### PR öncesi
```bash
pytest -v --cov
make lint
npx playwright test tests/e2e/critical-path.spec.ts
pytest tests/eval/  # prompt değiştiyse
```

### Merge sonrası (CI)
GitHub Actions:
- lint → unit → integration → eval (cached) → E2E (smoke) → build
- Failure → merge engellenir + issue otomatik açılır

### Production deploy sonrası
```bash
curl -fsS https://nodrat.com/api/health
curl -fsS https://nodrat.com/api/readiness
restic check
```

---

## 4. Eval Framework

### Golden test set
```text
tests/eval/golden_sets/
├── query_planner.yaml       (MVP-1: 20 örnek)
├── agenda_card.yaml         (MVP-1: 10)
├── content_generator.yaml   (MVP-1: 20)
├── hallucination_traps.yaml (200 zorlu)
└── sensitive_entities.yaml  (50 politik figür)
```

### Halüsinasyon detector
```text
1. NER → entities (kişi, kurum, tarih)
2. Her entity context article'larda var mı?
3. Yoksa: hallucination flag
4. Tarih: published_at range'inde mi?
5. LLM-as-judge: cümle context'te destekleniyor mu?

hallucination_rate = halu_count / total_entities
hedef: <0.02
```

### PII redaction test
```text
- Email regex test
- TC kimlik luhn check
- IP, IBAN, UUID
- Türkçe + İngilizce
- Edge case: kullanıcı kendi yazdı

Komut: pytest tests/eval/test_pii_redaction.py
Hedef: ≥%99 effectiveness
```

---

## 5. Raporlama

### Başarılı
```text
✅ <test türü>: <X/Y> geçti, coverage: %Z
   Süre: <T>s
   LLM: halu rate, citation rate
```

### Başarısız (kök neden)
```text
❌ <test türü>: <X/Y> geçti

Kök neden:
1. <test_id>: <hata>
   Olası neden: <hipotez>
   İlgili doküman: <path §X>
   Önerilen fix: <somut adım>

Önerilen aksiyon:
  a. Issue aç → "type:bug,priority:high"
  b. Fix branch
  c. TDD: önce test, sonra fix
```

### LLM eval
```text
═══════════════════════════════════════
LLM Eval — <prompt_name> v<version>
═══════════════════════════════════════
Provider/Model: <provider>/<model>
Test seti:      <count> örnek

✅ Schema validation:    <X/Y> (≥%99)
✅ Intent accuracy:      <X/Y> (≥%95)
✅ Hallucination rate:   <X.X%> (<%2)
✅ Citation rate:        <X.X%> (=100%)
✅ Quote cap (≤25):      <X/Y> (=100%)
✅ INSUFFICIENT_DATA:    <X/Y> (>%90)

Failed examples:
  - qp_007: intent yanlış (comparison vs current)
    Reason: "vs" pickup yok

Recommended actions:
  1. Prompt'a örnek ekle
  2. ...
═══════════════════════════════════════
```

---

## 6. Test Ekleme Kuralları

ZORUNLU test yazılması gereken durumlar:
```text
✅ Yeni endpoint           → integration + 1 unit test
✅ Yeni service             → unit test
✅ Yeni LLM prompt          → eval test (≥5 örnek)
✅ Bug fix                  → regression test
✅ Yeni DB tablosu          → migration test
✅ Yeni provider adapter    → mock test
✅ Yeni queue worker        → integration test
✅ Pricing/quota değişimi   → quota enforcement test
✅ Auth değişimi            → auth bypass test
```

---

## 7. Anti-pattern (HARD STOP)

```text
🛑 Test'i atlamak — "küçük değişiklik"
🛑 Production token ile test çağrısı
🛑 Mock'suz production DB'ye karşı test
🛑 Failing test'i comment-out
🛑 Coverage % düşürmek
🛑 Eval test setini küçültmek
🛑 Halü test'i geçmiş diye prompt rule'u zayıflatmak
🛑 Production'da debug print/log
🛑 Sensitive data test fixture (gerçek email)
🛑 Test'in yaptığını anlamadan PR onaylamak
```

---

## 8. Hızlı şablonlar

### Tüm testler
```bash
make test  # veya pytest -v --cov && cd apps/web && npm test
```

### Sadece son değişen modül
```bash
pytest tests/unit/test_$(basename $(git diff --name-only HEAD~1 | head -1) .py).py -v
```

### Coverage
```bash
pytest --cov=apps/api --cov-report=html && open htmlcov/index.html
```

### E2E smoke
```bash
npx playwright test tests/e2e/critical-path.spec.ts --headed
```

---

## 9. Test Eksikliği

Aşağıda kullanıcıya HATIRLAT:
```text
- PR'da yeni test yok       → "Test eklenmeli mi?"
- Coverage düşmüş           → "Hangi modül test edilmedi?"
- Bug fix regression yok    → ZORUNLU ekle
- Yeni endpoint integration → ZORUNLU ekle
- Prompt değişti eval yok   → ZORUNLU ekle
```

---

**ZORUNLU:** Bu komutla başlayan her istek ilgili kalite eşiklerini doğrular ve kök neden analiziyle raporlar.

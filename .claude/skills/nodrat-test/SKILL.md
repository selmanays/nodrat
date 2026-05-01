---
name: nodrat-test
description: Nodrat test ve kalite kontrol akışı. Kullanıcı "nodrat-test" ile başlayan komut verdiğinde zorunlu invoke edilir. Unit / integration / E2E / LLM evaluation testlerini koşar, kalite eşiklerini doğrular, başarısız olanlarda kök neden analizi yapar.
---

# Nodrat Test Skill — Kullanım Protokolü

Bu skill, kullanıcı "nodrat-test ..." ile başlayan bir komut verdiğinde zorunlu olarak çalışır. Test türünü tespit eder, ilgili komutları koşar, sonuçları raporlar ve başarısızlık durumunda kök neden analizi sunar.

---

## Aşama 0 — Ön kontrol

```text
[ ] Kullanıcının isteği "nodrat-test" ile başlıyor mu?
[ ] Test ortamı hazır mı? (test DB, fixtures, mock provider'lar)
[ ] Hangi test türü çalıştırılacak belirlendi mi?
[ ] Test'ler bir issue/PR ile ilişkili mi? (varsa GitHub'a raporla)
```

---

## 1. Test Türleri

### 1.1 Unit testler

```text
Konum:    tests/unit/
Tool:     pytest (Python), vitest (TS)
Coverage: hedef ≥%70 (kritik path'lerde ≥%85)
Süre:     <30 saniye toplam

Komutlar:
  pytest tests/unit/ -v
  pytest tests/unit/test_<module>.py::test_<func> -v
  pytest --cov=apps/api --cov-report=term-missing

Frontend:
  cd apps/web && npm test
  cd apps/web && npm run test:coverage
```

### 1.2 Integration testler

```text
Konum:    tests/integration/
Tool:     pytest + testcontainers
Süre:     <5 dk

Test edilenler:
  - DB migration + seed
  - API endpoint + DB
  - Worker + queue + DB
  - Provider mock + retry/fallback
  - Auth flow

Komutlar:
  pytest tests/integration/ -v
  docker compose -f docker-compose.test.yml up -d
  pytest tests/integration/test_<area>.py
  docker compose -f docker-compose.test.yml down
```

### 1.3 E2E testler

```text
Konum:    tests/e2e/
Tool:     Playwright
Süre:     <10 dk

Senaryolar:
  - Register → verify → first generation → save (aha moment)
  - Login → quota tracking
  - Admin source ekleme akışı
  - Insufficient data UX
  - Pricing → checkout (mock)

Komutlar:
  npx playwright test
  npx playwright test tests/e2e/aha-moment.spec.ts
  npx playwright test --headed (görsel debug)
```

### 1.4 LLM Evaluation

```text
Konum:    tests/eval/
Tool:     Custom pytest + LLM-as-judge
Süre:     <15 dk (provider rate limit'e göre)

Test edilenler:
  - Query Planner: structured JSON validity, intent doğruluğu
  - Agenda Card: halüsinasyon oranı, source coverage
  - Content Generator: 25 kelime quote cap, citation %100
  - Halüsinasyon test seti: golden examples
  - Sensitive entity check: politik figür için ekstra kural

Komutlar:
  pytest tests/eval/test_query_planner.py
  pytest tests/eval/test_agenda_card.py
  pytest tests/eval/test_content_generator.py
  pytest tests/eval/test_hallucination.py
  pytest tests/eval/ -v --eval-report
```

---

## 2. Kalite Eşikleri (Quality Gates)

### 2.1 Otomatik kontrol

Bu eşikler CI/CD pipeline'da otomatik doğrulanır. Düşürülürse merge engellenir.

```text
Test coverage           : ≥ %70 (kritik modüllerde ≥%85)
Lint pass               : 100% (ruff, black, eslint, prettier)
Type check pass         : 100% (mypy strict, tsc strict)
Unit test pass          : 100%
Integration test pass   : 100%
```

### 2.2 LLM kalite eşikleri

```text
Hallucination rate            : < %2  (golden test set)
Generation success rate       : > %95
Source citation rate          : 100%  (her output kaynaklı)
Schema validation pass        : ≥ %99 (Pydantic strict)
Direct quote 25-word cap      : 100%  (output validator)
INSUFFICIENT_DATA accuracy    : > %90 (positive tetikleme)
PII redaction effectiveness   : ≥ %99 (regex + LLM-as-judge)
Sensitive entity attribution  : 100% (politik figür "iddia edildi")
```

### 2.3 UX/UI kalite eşikleri

```text
Latency p95                   : Generate < 8s
                                Page load < 2s
                                Search < 1s
WCAG AA compliance            : 100% (Faz 6 öncesi audit)
Browser desteği               : Chrome, Safari, Firefox son 2 sürüm
Mobile responsive             : Tablet+
```

---

## 3. Test Koşum Akışı

### 3.1 Local geliştirme sırasında

```bash
# Hızlı geri bildirim — sadece değişen modülün testi
pytest tests/unit/test_<changed_module>.py -v

# Lint + type check
ruff check . && black --check . && mypy apps/api

# Frontend
cd apps/web && npm run lint && npm run type-check && npm test
```

### 3.2 PR açmadan önce

```bash
# Tüm unit + integration
pytest -v --cov

# Lint zinciri
make lint  # veya tek tek komutlar

# E2E (kritik akış)
npx playwright test tests/e2e/critical-path.spec.ts

# LLM eval (prompt değiştiyse)
pytest tests/eval/ -v
```

### 3.3 Merge sonrası (CI)

```text
GitHub Actions:
  - lint
  - unit tests
  - integration tests
  - LLM eval (cache'lenmiş örneklerle)
  - E2E (smoke tests)
  - Build artifact

Failure → merge engellenir, issue otomatik açılır.
```

### 3.4 Production deploy sonrası

```bash
# Smoke test (Architecture §8 ile uyumlu)
curl -fsS https://nodrat.com/api/health
curl -fsS https://nodrat.com/api/readiness

# Generation smoke
# (test user ile 1 generation, save kontrol)

# Backup health
restic check
```

---

## 4. Eval Framework — LLM Test Setleri

### 4.1 Golden test set yapısı

```text
tests/eval/golden_sets/
├── query_planner.yaml       (100 örnek hedef, MVP-1: 20)
├── agenda_card.yaml         (50 hedef, MVP-1: 10)
├── content_generator.yaml   (100 hedef, MVP-1: 20)
├── hallucination_traps.yaml (200 zorlu örnek)
└── sensitive_entities.yaml  (50 politik figür örneği)
```

Her örnek format:

```yaml
- id: qp_001
  description: "Bugünkü ekonomi gündemi → x_post"
  input:
    user_request: "..."
    current_time: "..."
  expected:
    intent: "current_content_generation"
    mode: "current"
    output_type: "x_post"
  pass_criteria:
    - intent == expected.intent
    - mode == expected.mode
  manual_review: false
```

### 4.2 Halüsinasyon tespiti (LLM-as-judge)

```text
Akış:
  1. NER ile çıktıdan entities çıkar (kişi, kurum, tarih)
  2. Her entity context article'larda var mı?
  3. Yoksa: hallucination flag
  4. Tarih: published_at range'inde mi?
  5. LLM-as-judge: "bu cümle context'te destekleniyor mu?"

Sonuç:
  hallucination_rate = halu_count / total_entities
  hedef: < 0.02
```

### 4.3 PII redaction testi

```text
Test cases:
  - Kullanıcı email yazdı → [email_redacted] olmalı
  - TC kimlik 11 hane → [id_redacted]
  - IP address → [ip_redacted]
  - IBAN → [iban_redacted]
  - UUID → [ref_redacted]
  - Karışık string'lerde tespit

Komut:
  pytest tests/eval/test_pii_redaction.py -v
```

### 4.4 Sensitive entity testi

```text
Politik figür / kamu görevlisi geçen test örnekleri:
  - "Cumhurbaşkanı X dedi" → kaynaklı ise OK
  - Kaynaksız iddia → reject + warning

Komut:
  pytest tests/eval/test_sensitive_entity.py -v
```

---

## 5. Test Sonucu Raporlama

### 5.1 Başarılı durum

```text
✅ <test türü>: <X/Y> geçti, coverage: %Z
   Süre: <T> saniye
   Eval örnekleri (LLM): <halu rate, citation rate>
```

### 5.2 Başarısız durum (kök neden analizi)

```text
❌ <test türü>: <X/Y> geçti, <FAILED> failures

Kök neden analizi:
1. <test_id>: <hata mesajı>
   Olası neden: <root cause hipotezi>
   İlgili doküman: <path §X>
   Önerilen fix: <somut adım>

2. ...

Önerilen aksiyon:
  a. Issue aç ve "type:bug" + "priority:high" etiketle
  b. Fix branch oluştur
  c. Test öncelikli (TDD): önce test yaz, sonra fix
```

### 5.3 LLM eval sonuç şablonu

```text
═══════════════════════════════════════════════════
LLM Eval Report — <prompt_name> v<version>
═══════════════════════════════════════════════════
Tarih:           <YYYY-MM-DD HH:MM>
Provider/Model:  <provider> / <model>
Test seti:       <count> örnek

✅ Schema validation:    <X/Y> (≥%99 hedef: <pass/fail>)
✅ Intent accuracy:      <X/Y> (≥%95 hedef: <pass/fail>)
✅ Hallucination rate:   <X.X%> (<%2 hedef: <pass/fail>)
✅ Citation rate:        <X.X%> (=100% hedef: <pass/fail>)
✅ Quote cap (≤25 word): <X/Y> (=100% hedef: <pass/fail>)
✅ INSUFFICIENT_DATA:    <X/Y> doğru tetiklendi (>%90 hedef)

Failed examples:
  - qp_007: intent yanlış: comparison yerine current
    Reason: "vs" kelimesi pickup edilmedi
  - ag_023: hallucination flag — "X kişisi şunu söyledi" kaynakta yok

Recommended actions:
  1. Query Planner prompt'a 'vs/karşılaştır' örneği ekle
  2. Agenda Card prompt'da source citation rule güçlendir
═══════════════════════════════════════════════════
```

---

## 6. Test Eklemenin Kuralları

### 6.1 Hangi durumda test yazmak ZORUNLU

```text
✅ Yeni endpoint                 → integration test + 1 unit test
✅ Yeni service / business logic → unit test
✅ Yeni LLM prompt               → eval test (en az 5 örnek)
✅ Bug fix                       → regression test (önce başarısız, sonra başarılı)
✅ Yeni DB tablosu               → migration test
✅ Yeni provider adapter         → mock test
✅ Yeni queue worker             → integration test
✅ Pricing/quota değişimi        → quota enforcement test
✅ Auth değişimi                 → auth bypass test
```

### 6.2 Test isimlendirme

```text
test_<unit_under_test>_<scenario>_<expected_outcome>

Örnekler:
  test_pii_redaction_email_replaces_with_placeholder
  test_query_planner_comparison_request_returns_two_timeframes
  test_generation_quota_exceeded_returns_403
  test_robots_txt_disallow_blocks_source_addition
```

### 6.3 Test fixture'ları

```text
tests/fixtures/
├── articles.json           (sample haber verisi)
├── sources.json            (3 örnek RSS kaynak)
├── prompts/                (test prompt örnekleri)
├── mock_providers.py       (DeepSeek/Anthropic mock)
└── test_db.sql             (test DB seed)
```

---

## 7. CI/CD Test Stratejisi

### 7.1 Pull Request hooks

```yaml
# .github/workflows/test.yml — schematik
on: pull_request
jobs:
  lint:
    - ruff check
    - black --check
    - mypy apps/api --strict
    - cd apps/web && npm run lint
  unit:
    - pytest tests/unit/ --cov
  integration:
    - docker compose up -d (test stack)
    - pytest tests/integration/
  eval (eğer prompt/RAG değiştiyse):
    - pytest tests/eval/ (cached LLM responses, ücretsiz)
  e2e (smoke):
    - npx playwright test tests/e2e/smoke.spec.ts
```

### 7.2 Main branch hooks

```yaml
on: push to main
jobs:
  full-test-suite (yukarıdakilerle aynı + complete e2e)
  deploy-staging
  smoke-test-staging
  (manual approval)
  deploy-production
  smoke-test-production
```

---

## 8. Anti-pattern (Test'te yapılmayacaklar)

```text
🛑 Test'i atlamak — "küçük değişiklik, test gereksiz"
🛑 LLM provider'ına gerçek prod token ile test çağrısı
🛑 Test'i mock olmadan production DB'ye karşı koşmak
🛑 Failing test'i comment-out etmek
🛑 Coverage % düşürmek (sadece artırılır)
🛑 Eval test setini küçültmek (sadece büyür)
🛑 Halüsinasyon test'i geçmiş diye prompt rule'u zayıflatmak
🛑 Production'da debug log/print bırakmak
🛑 Sensitive data'yı test fixture'una koymak (gerçek email, vb.)
🛑 Test'in yaptığını anlamadan PR onaylamak
```

---

## 9. Hızlı Komut Şablonları

### Tüm testleri koş
```bash
make test  # veya
pytest -v --cov && cd apps/web && npm test
```

### Sadece son değişen modül
```bash
pytest tests/unit/test_$(basename $(git diff --name-only HEAD~1 | head -1) .py).py -v
```

### LLM eval (sadece prompt değiştiyse)
```bash
pytest tests/eval/ --eval-report
```

### Coverage raporu
```bash
pytest --cov=apps/api --cov-report=html
open htmlcov/index.html
```

### E2E smoke
```bash
npx playwright test tests/e2e/critical-path.spec.ts --headed
```

---

## 10. Test Eksikliği Tespiti

Aşağıdaki durumlarda kullanıcıya hatırlat:

```text
- PR açılmış ama yeni test yok → "Test eklenmeli mi?"
- Coverage düşmüş → "Hangi modül test edilmedi?"
- Bug fix PR'da regression test yok → ZORUNLU ekle
- Yeni endpoint, integration test yok → ZORUNLU ekle
- Prompt değişimi, eval örneği eklenmedi → ZORUNLU ekle
```

---

**Bu skill ile başlayan her istek, ilgili kalite eşiklerini doğrular ve kök neden analiziyle raporlar. Atlanması: kabul edilemez.**

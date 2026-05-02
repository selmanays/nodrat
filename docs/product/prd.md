# PRD — Admin Kontrollü Haber Havuzu, RAG Tabanlı Gündem İçerik Üretim SaaS’i

**Doküman türü:** Product Requirements Document  
**Sürüm:** v0.1  
**Hedef çıktı:** Teknik ekip ve yapay zeka ajanları tarafından uygulanabilir geliştirme planı  
**Varsayılan dağıtım:** Tek VPS üzerinde self-hosted altyapı  
**Harici ücretli altyapı politikası:** İlk MVP’de ücretli altyapı yok; gelecekte yalnızca yapay zeka API sağlayıcıları ve ödeme sağlayıcıları entegre edilebilir.  
**Ana kullanım senaryosu:** Sistem yöneticisi güvenilir haber kaynaklarını tanımlar; sistem haberleri ve görselleri toplar, temizler, indeksler; kullanıcı kendi gündem talebini yazar; sistem mevcut haber havuzuna dayanarak X içerikleri, özetler, karşılaştırmalar ve analizler üretir.

---

## 1. Ürün özeti

Bu ürün, yönetici tarafından kontrol edilen haber kaynaklarından güncel içerikleri toplayan, bunları temizleyip arşivleyen, RAG tabanlı aranabilir bir bilgi havuzuna dönüştüren ve son kullanıcıların doğal dilde yazdığı gündem taleplerine göre X/Twitter içerikleri üreten bir SaaS platformudur.

Kullanıcılar haber kaynağı ekleyemez. Haber kaynakları, veri güvenliği ve kalite kontrol amacıyla sadece sistem yöneticisi tarafından eklenir ve yönetilir.

Ürün ilk aşamada metin tabanlı haber toplama ve içerik üretimi üzerine kurulacaktır. Daha sonra görsel arşivleme, görsel etiketleme, admin onaylı görsel bilgi tabanı, kullanıcı stili çıkarımı, abonelik sistemi ve ücretli/ücretsiz kullanım ayrımı eklenecektir.

---

## 2. Ana hedefler

### 2.1 Ürün hedefleri

1. Yönetici kontrollü güvenilir haber kaynakları havuzu oluşturmak.
2. Haberleri RSS veya kategori liste sayfalarından düzenli olarak toplamak.
3. RSS ile gelen haberlerde sadece RSS içeriğine güvenmeyip, haberin detay sayfasına giderek tam metni kazımak.
4. Kategori sayfası eklenen kaynaklarda haber kartlarını, başlıkları, linkleri, görselleri ve detay sayfası yapılarını yönetici tarafından ayarlanabilir hale getirmek.
5. Kazınan haberleri temizlemek, normalize etmek, duplicate içerikleri azaltmak ve arşivlemek.
6. Haber görsellerini ilk fazdan itibaren arşivlemek.
7. Haber içeriklerini RAG sistemine uygun şekilde chunk’lamak, embedlemek ve vektör tabanlı aranabilir hale getirmek.
8. Kullanıcıların doğal dille yazdığı gündem taleplerini sistemdeki haber havuzuyla eşleştirmek.
9. Kullanıcılara güncel, arşivli veya karşılaştırmalı içerikler üretebilmek.
10. İlk MVP’de NVIDIA NIM ücretsiz/prototip endpoint’leriyle çalışabilecek; gelecekte OpenRouter, DeepSeek, OpenAI, yerel LLM veya başka sağlayıcılarla değiştirilebilir bir model provider katmanı kurmak.
11. Tek VPS üzerinde çalışan, kuyruk tabanlı, ölçeklenebilir ve maliyet kontrollü bir sistem kurmak.
12. Ücretli abonelik sistemi eklenene kadar kullanım limitlerini yerel uygulama mantığıyla yönetmek.
13. İleride kullanıcı stili klonlama/uyarlama ve görsel destekli içerik üretimi eklemek.

---

## 3. Kapsam

### 3.1 Kapsam dahilinde

- Admin paneli
- Haber kaynağı yönetimi
- RSS kaynak yönetimi
- Kategori liste sayfası tabanlı kaynak yönetimi
- Haber detay sayfası kazıma ayarları
- Selector test aracı
- Haber temizleme ve normalize etme
- Görsel indirme ve arşivleme
- Duplicate haber tespiti
- Dil tespiti
- Kaynak güvenilirlik puanı
- İçerik kalitesi kontrolü
- RAG altyapısı
- Vector DB
- Gündem kartı üretimi
- Zaman filtreli retrieval
- Karşılaştırmalı retrieval
- Kullanıcı dashboard’u
- Doğal dil gündem girişi
- X paylaşımı üretimi
- Thread üretimi
- İçerik geçmişi
- Kaynak gösterimli çıktı
- Görsel etiketleme admin sistemi
- Stil profili çıkarma fazı
- Abonelik ve ücretsiz deneme fazı
- Kuyruk, worker, retry, dead-letter mekanizmaları
- Self-hosted deployment
- Observability, loglama, yedekleme

### 3.2 Kapsam dışında — MVP için

- Kullanıcıların kendi haber kaynaklarını eklemesi
- Otomatik X paylaşımı gönderme
- Gerçek zamanlı sosyal medya scraping
- Tam otomatik yüz tanıma ile kesin kişi iddiası
- Telif hakkı ihlali oluşturabilecek tam haber yeniden yayınlama
- Mobil uygulama
- Kurumsal ekip yönetimi
- Çok bölgeli dağıtım
- Kubernetes zorunluluğu
- Büyük ölçekli fine-tuning

---

## 4. Kullanıcı rolleri

### 4.1 Super Admin / Sistem Yöneticisi

Yetkileri:

- Haber kaynağı ekler.
- RSS kaynağı ekler.
- Kategori liste sayfası ekler.
- Haber liste kartı selector’larını ayarlar.
- Haber detay sayfası selector’larını ayarlar.
- Kaynak aktif/pasif durumunu yönetir.
- Kaynak tarama sıklığını belirler.
- Kaynak güvenilirlik puanını belirler.
- Haberleri ve görselleri inceler.
- Temizleme hatalarını düzeltir.
- Görsellere manuel etiket verir.
- Model provider ayarlarını yönetir.
- Kuyruk ve worker durumlarını izler.
- Kullanıcıları ve paketleri yönetir.
- Sistem ayarlarını yönetir.

### 4.2 Registered User

Yetkileri:

- Dashboard’a giriş yapar.
- Gündem talebi yazar.
- Zaman modunu seçer: güncel, haftalık, arşivli analiz, karşılaştırma.
- İçerik türü seçer: X post, thread, özet, analiz, başlık önerisi.
- Ton seçer.
- İçerik üretir.
- Üretilen içerikleri kaydeder.
- Kullanım geçmişini görür.
- İleride stil profili oluşturur.

### 4.3 Guest / Trial User

Yetkileri:

- Sınırlı sayıda ücretsiz deneme yapar.
- Daha düşük kaliteli/ücretsiz model provider ile cevap alır.
- Kaynak detaylarının sınırlı versiyonunu görür.
- Üyelik/abonelik çağrısı görür.

---

## 5. Genel sistem mimarisi

```text
[Admin Panel]
     |
     v
[Source Manager]
     |
     v
[Scheduler] ---> [Queue: source_discovery_jobs]
     |
     v
[Scraper Workers]
     |
     v
[Raw Article Store] ---> [Media Downloader] ---> [Image Archive]
     |
     v
[Cleaning + Normalization Workers]
     |
     v
[Article Chunking]
     |
     v
[Embedding Workers]
     |
     v
[PostgreSQL + pgvector]
     |
     v
[Event Clustering + Agenda Card Workers]
     |
     v
[Agenda/Event Knowledge Layer]
     |
     v
[User Dashboard] ---> [Query Planner] ---> [Retriever] ---> [LLM Generator]
```

---

## 6. Önerilen self-hosted teknik stack

### 6.1 İlk MVP için önerilen stack

```text
Frontend:
- Next.js
- Tailwind CSS
- shadcn/ui

Backend API:
- FastAPI veya NestJS
- MVP önerisi: FastAPI, çünkü scraping, NLP ve RAG worker’ları Python ekosistemiyle daha hızlı entegre olur.

Database:
- PostgreSQL
- pgvector extension

Queue:
- Redis
- Celery veya RQ
- MVP önerisi: Celery + Redis

Object Storage:
- MinIO
- Haber görselleri, HTML snapshot’ları, debug çıktıları için

Crawler/Scraper:
- Python requests/httpx
- BeautifulSoup/lxml
- trafilatura veya readability-lxml
- Playwright, yalnızca JS render gerektiren kaynaklarda

Scheduler:
- Celery Beat
- Alternatif: APScheduler

Search:
- pgvector semantic search
- Opsiyonel keyword search: PostgreSQL full-text search
- İleri fazda Meilisearch veya Typesense eklenebilir.

Reverse Proxy:
- Caddy veya Nginx

Process/Container:
- Docker Compose
- İleri fazda k3s veya Docker Swarm opsiyonel

Observability:
- Prometheus
- Grafana
- Loki veya basit dosya tabanlı log + admin log ekranı

Model Provider:
- NVIDIA NIM provider
- OpenRouter provider
- DeepSeek provider
- OpenAI-compatible generic provider
- Local Ollama/vLLM provider, opsiyonel
```

### 6.2 VPS minimum başlangıç önerisi

MVP test:

```text
CPU: 4 vCPU
RAM: 8–16 GB
Disk: 100–200 GB SSD
OS: Ubuntu LTS
```

Daha ciddi kullanım:

```text
CPU: 8–16 vCPU
RAM: 32 GB
Disk: 500 GB+ NVMe
Ek disk: Görsel arşivi için ek blok storage veya ikinci disk
```

Not: İlk aşamada model inference dış API üzerinden yapılacağı için GPU zorunlu değildir. Gelecekte yerel model çalıştırılacaksa GPU’lu sunucu ayrı değerlendirilmelidir.

---

## 7. Faz planı

## Faz 0 — Altyapı temelinin kurulması

### Amaç

Sistemin ileride büyüyebilmesi için temel backend, veritabanı, queue, worker, storage ve deployment altyapısını kurmak.

### Gereksinimler

#### F0-R1 — Monorepo veya servis yapısı

Sistem şu klasör yapısıyla başlayabilir:

```text
/apps
  /web               # Next.js frontend
  /api               # FastAPI/NestJS API
  /admin             # Admin panel, web içinde de olabilir
/workers
  /scraper
  /cleaner
  /embedding
  /rag
  /media
  /vision
/packages
  /shared-types
  /model-providers
  /crawler-core
  /rag-core
/infra
  docker-compose.yml
  nginx-or-caddy
  postgres
  redis
  minio
/docs
  prd.md
  architecture.md
  api.md
```

#### F0-R2 — Docker Compose

Aşağıdaki servisler Docker Compose ile ayağa kalkmalıdır:

```text
web
api
postgres
redis
minio
worker_scraper
worker_cleaner
worker_embedding
worker_rag
scheduler
```

#### F0-R3 — Ortam değişkenleri

```env
DATABASE_URL=
REDIS_URL=
MINIO_ENDPOINT=
MINIO_ACCESS_KEY=
MINIO_SECRET_KEY=
NVIDIA_NIM_API_KEY=
OPENROUTER_API_KEY=
DEEPSEEK_API_KEY=
DEFAULT_LLM_PROVIDER=nvidia_nim
DEFAULT_EMBEDDING_PROVIDER=nvidia_nim
DEFAULT_RERANK_PROVIDER=nvidia_nim
```

#### F0-R4 — Provider abstraction

Model çağrıları hiçbir yerde doğrudan tek sağlayıcıya bağlı olmamalıdır.

```text
ModelProvider
- generateText()
- generateStructuredJson()
- createEmbedding()
- rerank()
- analyzeImage()
- transcribeOrOcr(), opsiyonel
```

Her sağlayıcı adapter olarak yazılmalıdır:

```text
NvidiaNimProvider
OpenRouterProvider
DeepSeekProvider
OpenAICompatibleProvider
LocalProvider
```

### Kabul kriterleri

- Sistem tek komutla lokal veya VPS üzerinde ayağa kalkar.
- API healthcheck çalışır.
- Worker healthcheck çalışır.
- PostgreSQL, Redis ve MinIO bağlantıları doğrulanır.
- Model provider test endpoint’i mock veya gerçek sağlayıcı ile test edilebilir.

---

# Faz 1 — Admin kontrollü kaynak yönetimi, haber kazıma, temizleme ve görsel arşivleme

## 1.1 Amaç

Sistem yöneticisi haber kaynaklarını tanımlayabilmeli. Sistem bu kaynaklardan RSS veya kategori liste sayfası üzerinden haberleri keşfetmeli, detay sayfalarına giderek tam haber içeriğini kazımalı, metni temizlemeli, görselleri indirmeli ve arşivlemelidir.

---

## 1.2 Kaynak türleri

### Source Type A — RSS kaynağı

Admin şunları girer:

```text
Kaynak adı
Kaynak domain
RSS URL
Dil
Kategori
Tarama sıklığı
Kaynak güvenilirlik puanı
RSS item link alanı
RSS item title alanı
RSS item published date alanı
RSS item image alanı, varsa
Detay sayfası kazıma yöntemi
```

RSS akışı sadece keşif için kullanılmalıdır. Tam haber metni için RSS item içindeki `link` üzerinden haber detay sayfasına gidilmelidir.

### Source Type B — Kategori liste sayfası

Admin şunları girer:

```text
Kaynak adı
Kategori URL’i
Liste sayfası selector ayarları
Haber kartı selector’ı
Başlık selector’ı
Link selector’ı
Görsel selector’ı
Tarih selector’ı, varsa
Pagination ayarı
Tarama sıklığı
Detay sayfası kazıma yöntemi
```

Örnek:

```json
{
  "sourceType": "category_page",
  "categoryUrl": "https://example.com/siyaset",
  "listSelectors": {
    "card": ".news-card",
    "title": ".news-card h2",
    "link": ".news-card a",
    "image": ".news-card img",
    "date": ".news-date"
  },
  "pagination": {
    "type": "none|next_link|page_param|infinite_scroll",
    "nextSelector": ".pagination .next",
    "pageParam": "page"
  }
}
```

### Source Type C — Manuel detay URL import

Admin tekil haber URL’i ekleyebilmelidir.

Bu özellik debug, test ve kaynak selector ayarı için kullanılacaktır.

---

## 1.3 Admin kaynak ekleme akışı

```text
1. Admin kaynak türünü seçer.
2. URL girer.
3. Sistem URL’i test eder.
4. Sistem HTML veya RSS içeriğini çeker.
5. Admin selector’ları tanımlar.
6. Sistem canlı önizleme gösterir.
7. Admin örnek haberleri görür.
8. Admin detay sayfası extractor ayarlarını test eder.
9. Admin kaynağı aktif eder.
10. Scheduler bu kaynağı belirlenen aralıklarla taramaya başlar.
```

---

## 1.4 Selector test aracı

Admin panelde mutlaka selector test ekranı olmalıdır.

### Liste sayfası test ekranı

Gösterilecek alanlar:

```text
Liste URL’i
HTML fetch status
Bulunan haber kartı sayısı
İlk 10 haber kartı preview
Başlık
Link
Görsel URL
Tarih
Hata/uyarı listesi
```

### Detay sayfası test ekranı

Gösterilecek alanlar:

```text
Detay URL’i
HTTP status
Final canonical URL
Başlık
Spot
Yayın tarihi
Yazar
Haber metni
Ana görsel
Galeri görselleri
HTML temizleme skoru
Metin uzunluğu
Paragraf sayısı
Boilerplate oranı
```

---

## 1.5 Haber detay sayfası kazıma

Her haber için detay sayfasına gidildiğinde şu alanlar çıkarılmalıdır:

```text
title
subtitle/spot
author
published_at
updated_at, varsa
category
tags
body_html
clean_text
main_image_url
gallery_image_urls
canonical_url
source_url
source_id
language
```

### Extractor stratejileri

Sistem üç kademeli çalışmalıdır:

```text
1. Kaynağa özel admin selector’ları
2. Genel readability/trafilatura extractor
3. Fallback: metadata + paragraph extraction
```

Sistem her haber için extraction confidence hesaplamalıdır.

```text
extraction_confidence =
title_found
+ body_length_score
+ paragraph_count_score
+ boilerplate_ratio_score
+ date_found
+ image_found
```

---

## 1.6 Temizleme ve normalizasyon

### Temizlenecek içerikler

- HTML tag’leri
- script/style/nav/footer
- reklam blokları
- sosyal medya paylaşım metinleri
- cookie banner metinleri
- tekrar eden paragraf
- tracking parametreleri
- boş satırlar
- bozuk Unicode karakterleri
- aşırı whitespace
- kod kalıntıları
- yorum alanları
- “Son Dakika”, “Abone Ol”, “Bizi takip edin” gibi kaynak-specific boilerplate ifadeler

### Normalizasyon

```text
URL canonicalization
Tarih normalize etme
Dil tespiti
Başlık trim
Metin segmentasyonu
Paragraf ayrıştırma
Kaynak adı eşleştirme
Görsel URL absolute hale getirme
```

---

## 1.7 Duplicate tespiti

Duplicate tespiti dört seviyede yapılmalıdır:

```text
1. Canonical URL duplicate
2. Title hash duplicate
3. Clean text hash duplicate
4. Semantic similarity duplicate, ileri faz
```

Minimum MVP:

```text
canonical_url unique
content_hash unique
normalized_title_hash
```

Aynı haber farklı kaynaklarda çıkarsa silinmemeli; bunun yerine aynı `event_cluster` altında toplanabilmelidir. Ancak aynı kaynaktan birebir aynı haber tekrar çekiliyorsa duplicate olarak işaretlenmelidir.

---

## 1.8 Görsel arşivleme — Faz 1 içinde başlar

Haberlerdeki görseller ilk fazdan itibaren arşivlenmelidir.

### Görsel kaynakları

```text
RSS image
Liste kartı image
Detay ana görsel
Detay galeri görselleri
OpenGraph image
Twitter card image
```

### Görsel işleme

Her görsel için:

```text
Görsel URL’i normalize edilir.
Görsel indirilir.
MIME type doğrulanır.
Dosya hash’i alınır.
Perceptual hash alınır.
Boyutlar çıkarılır.
MinIO’ya kaydedilir.
Haberle ilişkilendirilir.
```

### Görsel dosya path önerisi

```text
/images/{source_slug}/{yyyy}/{mm}/{dd}/{image_id}.{ext}
```

### Görsel metadata

```text
image_id
article_id
source_id
original_url
storage_url
mime_type
width
height
file_size
sha256_hash
perceptual_hash
caption
alt_text
discovered_from
created_at
```

---

## 1.9 Queue mimarisi — Faz 1

### Job türleri

```text
source.fetch_rss
source.fetch_category
article.discover
article.fetch_detail
article.extract
article.clean
media.discover
media.download
media.hash
article.dedupe
source.healthcheck
```

### Job priority

```text
high: manuel admin test işleri
normal: düzenli kaynak taramaları
low: eski haber yeniden işleme
```

### Retry politikası

```text
HTTP 429: exponential backoff, source-level cooldown
HTTP 5xx: 3 retry
Timeout: 2 retry
Parser error: retry yok, admin review kuyruğu
Media download error: 2 retry
```

### Dead letter queue

Başarısız işler `failed_jobs` tablosuna düşmelidir.

Admin panelde şu bilgiler görünmelidir:

```text
job_type
source_id
article_url
error_message
retry_count
last_attempt_at
stack_trace, sadece admin
```

---

## 1.10 Faz 1 veri modeli

### `sources`

```sql
id
name
slug
domain
type -- rss | category_page | manual
base_url
language
country
category
reliability_score
is_active
crawl_interval_minutes
last_crawled_at
created_at
updated_at
```

### `source_configs`

```sql
id
source_id
config_json
version
is_active
created_by
created_at
```

### `source_health`

```sql
id
source_id
last_status
last_success_at
last_failure_at
failure_count
avg_fetch_ms
avg_extract_confidence
last_error
```

### `articles`

```sql
id
source_id
canonical_url
source_url
title
subtitle
author
published_at
updated_at
crawled_at
raw_html_storage_path
body_html
clean_text
language
content_hash
title_hash
extraction_confidence
status -- discovered | fetched | cleaned | failed | archived
created_at
updated_at
```

### `article_images`

```sql
id
article_id
source_id
original_url
storage_url
caption
alt_text
mime_type
width
height
file_size
sha256_hash
perceptual_hash
discovered_from -- rss | listing | detail | opengraph | gallery
status -- downloaded | failed | duplicate | pending
created_at
```

### `crawler_jobs`

```sql
id
job_type
status
priority
payload_json
attempt_count
max_attempts
scheduled_at
started_at
finished_at
error_message
created_at
```

---

## 1.11 Faz 1 kabul kriterleri

- Admin RSS kaynağı ekleyebilir.
- Admin kategori liste sayfası ekleyebilir.
- Admin selector test edebilir.
- RSS item linklerinden detay haber kazınabilir.
- Kategori sayfasından haber kartları çıkarılabilir.
- Detay sayfasından başlık, metin, tarih ve görsel alınabilir.
- Haber metni temizlenmiş olarak kaydedilir.
- Görseller MinIO’ya kaydedilir.
- Duplicate haberler işaretlenir.
- Başarısız kaynaklar admin panelde görünür.
- Queue sistemi retry ve failed job yönetimi yapar.

---

# Faz 2 — RAG altyapısı, embedding, event clustering ve gündem kartları

## 2.1 Amaç

Toplanan haberleri RAG sistemine uygun hale getirmek. Haberler chunk’lanacak, embedlenecek, vector DB’ye kaydedilecek, benzer haberler olay kümelerine bağlanacak ve içerik üretimi için kısa gündem kartları oluşturulacaktır.

---

## 2.2 Temel RAG prensibi

Kullanıcı sorgusunda modele tüm haber arşivi gönderilmeyecektir.

Doğru akış (MVP-1.1 #169 + #171 PR-D + PR-E ile uygulandı):

```text
Kullanıcı talebi
↓
Query Planner (DeepSeek json_mode, output: topic_query + keywords[5])
↓
Zaman filtresi
↓
Hybrid Retrieval (#171 PR-E):
  - Dense: bge-m3 cosine similarity (agenda_cards.embedding)
  - Sparse: pg_trgm similarity (title + summary)
  - RRF (Reciprocal Rank Fusion, k=60)
↓
Threshold filter (semantic ≥ 0.55, trigram ≥ 0.15)
↓
Top-K agenda cards (default 10)
↓
[FALLBACK] Eğer agenda_cards 0 → article_chunks hybrid search
↓
LLM generation (DeepSeek json_mode + irrelevant_sources guard #167)
```

**Halüsinasyon koruması katmanları:**
1. Threshold (sparse + dense) → alakasız retrieve edilmez
2. LLM relevance check (#167) → alakasız kaynaklarla içerik üretmez
3. current_time payload'da (#169) → eski olay "şu an" sunulmaz

**Cache optimizasyonu (#171):** DeepSeek implicit prompt caching — system prompt'lar statik, cache hit %90+ hedef, cost <\$0.001/gen.

---

## 2.3 Chunking

Her haber aşağıdaki şekilde chunk’lanmalıdır:

```text
title + subtitle + paragraph group
```

Chunk hedefleri:

```text
Minimum: 200 token
İdeal: 400–700 token
Maksimum: 900 token
Overlap: 50–100 token
```

Her chunk içinde şu metadata tutulmalıdır:

```text
article_id
source_id
published_at
source_reliability_score
language
title
url
chunk_index
```

---

## 2.4 Embedding

### Model provider bağımsızlığı

Embedding sağlayıcısı ayarlanabilir olmalıdır:

```text
nvidia_nim
openrouter
deepseek, destekliyorsa
openai_compatible
local
```

### Embedding job akışı

```text
article.cleaned
↓
chunk oluştur
↓
embedding kuyruğuna at
↓
embedding provider çağır
↓
pgvector’a yaz
```

### `article_chunks`

```sql
id
article_id
source_id
chunk_index
chunk_text
token_count
embedding vector
published_at
created_at
```

---

## 2.5 Event clustering

Amaç: Aynı olaya ait farklı kaynak haberlerini tek olay altında toplamak.

### Clustering sinyalleri

```text
Başlık benzerliği
Embedding benzerliği
Yayın zamanı yakınlığı
Aynı kişi/kurum/yer ifadeleri
Aynı URL canonical veya benzer başlık
```

### MVP clustering kuralı

```text
Son 72 saat içinde
semantic_similarity > threshold
ve normalized_title_similarity > threshold
ise aynı event_cluster adayı
```

### `event_clusters`

```sql
id
canonical_title
current_summary
embedding vector
first_seen_at
last_seen_at
last_updated_at
status -- developing | active | cooling | stale | archived
importance_score
freshness_score
source_count
article_count
created_at
updated_at
```

### `event_articles`

```sql
id
event_id
article_id
source_id
published_at
relationship_score
created_at
```

---

## 2.6 Gündem kartları

Gündem kartı, içerik üretiminde modele verilecek ana bilgi nesnesidir.

### Gündem kartı amacı

Ham haber yerine kısa, güncel, kaynaklı ve üretime hazır bağlam sağlamak.

### `agenda_cards`

```sql
id
event_id
title
summary
key_points jsonb
content_angles jsonb
timeline jsonb
source_refs jsonb
status
freshness_score
importance_score
embedding vector
created_at
updated_at
```

### Gündem kartı örnek JSON

```json
{
  "title": "CHP'den ekonomi politikalarına ilişkin yeni açıklama",
  "summary": "CHP yönetimi, ekonomi politikaları üzerinden iktidara eleştiriler yöneltti ve yeni açıklamalar yaptı.",
  "key_points": [
    "Açıklama parti yönetimi tarafından yapıldı.",
    "Ekonomi ve geçim sıkıntısı vurgusu öne çıktı.",
    "Muhalefet söyleminde seçim çağrısı tonunun güçlendiği görülüyor."
  ],
  "content_angles": [
    "ekonomi eleştirisi",
    "gündem değişimi",
    "muhalefet söylemi",
    "seçim çağrısı"
  ],
  "source_refs": [
    {
      "source": "Kaynak adı",
      "title": "Haber başlığı",
      "url": "https://..."
    }
  ],
  "status": "active",
  "freshness_score": 0.91,
  "importance_score": 0.76
}
```

---

## 2.7 Zaman yönetimi

Sistem eski haberleri saklayacak fakat varsayılan üretimde eski haberleri kullanmayacaktır.

### Zaman modları

```text
current:
- Varsayılan mod
- Son 24–48 saat
- X post üretimi için önerilen mod

weekly:
- Son 7 gün
- Haftalık özet veya haftalık içerik planı

archive:
- Belirli tarih aralığı
- Geçmiş analiz

comparison:
- İki veya daha fazla dönem karşılaştırması
```

### Freshness score

```text
0–6 saat: 1.00
6–24 saat: 0.85
1–3 gün: 0.60
3–7 gün: 0.35
7–30 gün: 0.10
30+ gün: archive only
```

### Final retrieval score

```text
final_score =
semantic_similarity * 0.50
+ freshness_score * 0.25
+ importance_score * 0.15
+ source_reliability_score * 0.10
```

Current modda freshness ağırlığı artırılabilir:

```text
current_final_score =
semantic_similarity * 0.45
+ freshness_score * 0.35
+ importance_score * 0.10
+ source_reliability_score * 0.10
```

---

## 2.8 Query Planner

Kullanıcı talebi önce yapılandırılmış plana dönüştürülmelidir.

### Örnek kullanıcı talebi

```text
CHP'nin geçen ayki gündemiyle bu ayki gündemini kıyaslayan içerikler üret.
```

### Query Planner çıktısı

```json
{
  "intent": "comparative_content_generation",
  "topic_query": "CHP gündemi",
  "mode": "comparison",
  "timeframes": [
    {
      "label": "previous_month",
      "from": "2026-04-01",
      "to": "2026-04-30"
    },
    {
      "label": "current_month",
      "from": "2026-05-01",
      "to": "2026-05-31"
    }
  ],
  "output_type": "x_posts",
  "minimum_evidence_per_period": 3
}
```

### Desteklenecek intent türleri

```text
current_content_generation
weekly_summary_generation
archive_analysis
comparative_content_generation
thread_generation
headline_generation
source_based_briefing
```

---

## 2.9 Retrieval davranışı

### Current mode

```text
1. Son 24 saatte ara.
2. Yeterli sonuç yoksa son 48 saate genişlet.
3. Yeterli sonuç yoksa son 72 saate genişlet.
4. Hâlâ sonuç yoksa kullanıcıya veri yetersizliği bildir.
```

### Archive mode

```text
1. Kullanıcının verdiği tarih aralığını çöz.
2. O aralıkta agenda_cards veya article_chunks üzerinde arama yap.
3. Veri yeterliliğini kontrol et.
4. Cevabı tarih bağlamıyla üret.
```

### Comparison mode

```text
1. Her dönem için ayrı retrieval yap.
2. Her dönem için veri yeterliliğini kontrol et.
3. Dönemleri birbirine karıştırmadan LLM’e ayrı bloklar olarak gönder.
4. Önce fark analizini çıkar.
5. Sonra içerik üret.
```

---

## 2.10 Veri yeterliliği kontrolü

Sistem veri yoksa veya yetersizse içerik uydurmamalıdır.

Minimum kurallar:

```text
current mode:
- En az 2 agenda card veya
- En az 3 farklı haber

comparison mode:
- Her dönem için en az 2 agenda card veya
- Her dönem için en az 3 haber
- En az 2 farklı kaynak önerilir
```

Yetersiz veri mesajı örneği:

```text
Bu konu için seçilen dönemde yeterli güvenilir haber verisi bulunamadı. Güvenilir içerik üretimi için kapsamı genişletebilir veya farklı bir zaman aralığı seçebilirsiniz.
```

---

## 2.11 Model provider abstraction — Faz 2

### Provider config

```sql
model_providers
- id
- name
- type
- base_url
- api_key_secret_ref
- supports_chat
- supports_embeddings
- supports_rerank
- supports_vision
- is_active
- priority
```

### Model routing

```text
Trial user:
- free provider
- düşük max token
- düşük concurrency
- cache öncelikli

Paid user:
- premium provider
- daha yüksek max token
- daha yüksek concurrency
- gelişmiş modeller
```

### Fallback

```text
1. Primary provider başarısız olursa retry.
2. Aynı provider tekrar başarısız olursa secondary provider.
3. Provider quota error verirse düşük maliyetli provider’a geç.
4. Cevap kalitesi kritikse kullanıcıya gecikme/başarısızlık bildir.
```

---

## 2.12 Faz 2 kabul kriterleri

- Haberler chunk’lanabilir.
- Embedding üretilebilir.
- pgvector’da semantic search yapılabilir.
- Gündem kartları üretilebilir.
- Event clustering temel düzeyde çalışır.
- Current, archive ve comparison retrieval modları desteklenir.
- Veri yetersizliği durumunda sistem uydurma içerik üretmez.
- NVIDIA NIM provider ile MVP çalışabilir.
- Model provider değiştirilebilir yapıdadır.

---

# Faz 3 — Kullanıcı dashboard’u ve içerik üretim ekranı

## 3.1 Amaç

Kullanıcı sisteme giriş yaparak istediği gündemi doğal dille yazabilmeli ve sistem, admin kontrollü haber havuzundan aldığı bağlamla içerik üretebilmelidir.

---

## 3.2 Kullanıcı ana ekranı

Ana input:

```text
Hangi gündemle ilgili içerik üretmek istiyorsun?
```

Örnek placeholder:

```text
Örn: Bu hafta yapay zeka regülasyonlarıyla ilgili Türkiye ve dünyadaki gelişmeleri kullanarak 5 X paylaşımı üret.
```

### Parametreler

```text
İçerik türü:
- X paylaşımı
- X thread
- Gündem özeti
- Karşılaştırmalı analiz
- Başlık önerileri
- İçerik takvimi

Zaman modu:
- Güncel
- Son 7 gün
- Tarih aralığı
- Karşılaştırma

Ton:
- Tarafsız
- Eleştirel
- Mizahi
- Kurumsal
- Aktivist
- Analitik
- Sade
- Sert ama kaynaklı

Uzunluk:
- Kısa
- Orta
- Detaylı

Kaynak gösterimi:
- Göster
- Gizle
```

---

## 3.3 İçerik üretim akışı

```text
1. Kullanıcı talebi alınır.
2. Query Planner talebi yapılandırır.
3. Retriever ilgili gündem kartlarını getirir.
4. Veri yeterliliği kontrol edilir.
5. LLM içerik üretir.
6. Cevap kalite kontrolünden geçer.
7. Kullanıcıya içerik + kaynaklar + kullanılan gündem kartları gösterilir.
```

---

## 3.4 Üretilen cevap formatı

X paylaşımı örneği:

```json
{
  "content_type": "x_posts",
  "topic": "Kullanıcının gündemi",
  "data_coverage": {
    "mode": "current",
    "from": "2026-05-01T00:00:00",
    "to": "2026-05-01T23:59:59",
    "source_count": 5,
    "agenda_card_count": 3
  },
  "posts": [
    {
      "text": "Paylaşım metni...",
      "angle": "ekonomi eleştirisi",
      "related_agenda_card_ids": ["..."]
    }
  ],
  "sources": [
    {
      "title": "Haber başlığı",
      "source": "Kaynak",
      "url": "..."
    }
  ],
  "warnings": []
}
```

---

## 3.5 Halüsinasyon kontrolü

LLM prompt’unda şu kurallar zorunlu olmalıdır:

```text
Sadece verilen gündem kartlarını ve kaynak özetlerini kullan.
Context içinde olmayan iddia ekleme.
Tarih, kişi, kurum veya olay uydurma.
Eğer veri yetersizse içerik üretme; veri yetersizliği mesajı ver.
Eski bir olayı güncelmiş gibi sunma.
Kaynağı olmayan iddiaları kesin ifade etme.
```

---

## 3.6 Kullanıcı geçmişi

Kullanıcının ürettiği içerikler kaydedilmelidir.

### `generations`

```sql
id
user_id
request_text
mode
output_type
tone
retrieval_plan_json
used_agenda_card_ids
model_provider
model_name
input_tokens
output_tokens
cost_estimate
output_json
created_at
```

---

## 3.7 Kullanım limitleri

MVP’de ödeme yoksa bile limit sistemi kurulmalıdır.

```text
guest_daily_limit
free_user_daily_limit
paid_user_daily_limit
max_generations_per_hour
max_concurrent_generations_per_user
```

### `usage_events`

```sql
id
user_id
event_type
provider
model
input_tokens
output_tokens
created_at
```

---

## 3.8 Faz 3 kabul kriterleri

- Kullanıcı gündem talebi yazabilir.
- Sistem current, archive, comparison modlarını algılayabilir.
- Sistem veri havuzundan ilgili gündem kartlarını bulur.
- Kullanıcı X paylaşımı üretebilir.
- Kullanıcı kaynakları görebilir.
- Veri yetersizse sistem bunu açıkça bildirir.
- Üretim geçmişi kaydedilir.
- Kullanım limitleri uygulanır.

---

# Faz 4 — Görsel zeka, admin görsel etiketleme ve görsel RAG

## 4.1 Amaç

Faz 1’de arşivlenen haber görsellerini analiz etmek, açıklamak, embedlemek, admin tarafından doğrulanabilir etiketlere bağlamak ve içerik üretiminde görsel bağlam olarak kullanmak.

---

## 4.2 Kritik ürün prensibi

Sistem, görseldeki kişileri otomatik olarak kesin biçimde tanımlayan bir yüz tanıma ürünü gibi çalışmamalıdır.

Doğru yaklaşım:

```text
Otomatik öneri + admin onayı + güven skoru
```

Sistem şunu diyebilir:

```text
Bu görsel daha önce admin tarafından “Özgür Özel” olarak etiketlenmiş görsellere benziyor. Onay gerekiyor.
```

Sistem şunu dememelidir:

```text
Bu kişi kesin olarak Özgür Özel’dir.
```

---

## 4.3 Görsel analiz pipeline

```text
image.downloaded
↓
image.hash
↓
image.embedding
↓
VLM caption
↓
OCR
↓
object/scene tags
↓
admin review queue
↓
verified labels
```

---

## 4.4 Görsel analiz alanları

```sql
image_analysis
- image_id
- vlm_caption
- ocr_text
- detected_objects jsonb
- scene_tags jsonb
- auto_label_candidates jsonb
- confidence_json
- provider
- model_name
- created_at
```

```sql
image_embeddings
- image_id
- embedding vector
- provider
- model_name
- created_at
```

---

## 4.5 Entity registry

Tüm kişi, kurum, yer ve konu etiketleri merkezi entity tablosunda tutulmalıdır.

```sql
entities
- id
- type -- person | organization | location | topic | object | visual_type
- name
- aliases jsonb
- description
- created_by
- created_at
```

Örnek:

```json
{
  "type": "person",
  "name": "Özgür Özel",
  "aliases": ["Ozgur Ozel", "CHP Genel Başkanı"]
}
```

---

## 4.6 Admin görsel etiketleme ekranı

Her görsel için admin şunları görmelidir:

```text
Görsel preview
Bağlı haber başlığı
Kaynak
Yayın tarihi
Haber linki
VLM açıklaması
OCR sonucu
Model önerileri
Benzer doğrulanmış görseller
Etiket ekleme alanı
Kişi / kurum / yer / konu / görsel türü
Onayla / reddet / şüpheli işaretle
```

---

## 4.7 `image_labels`

```sql
id
image_id
entity_id
label_type
confidence
source -- model | admin | context | similarity
status -- suggested | verified | rejected | uncertain
verified_by
verified_at
created_at
```

---

## 4.8 Görsel içerik üretiminde kullanım

Kullanıcı görselli içerik isterse sistem:

```text
1. Gündem kartını bulur.
2. Gündem kartına bağlı haber görsellerini getirir.
3. Admin tarafından doğrulanmış etiketleri önceliklendirir.
4. Doğrulanmamış kişi iddialarını kullanmaz.
5. Görsel açıklamasıyla birlikte içerik üretir.
```

Prompt kuralı:

```text
Sadece verified görsel etiketlerini kesin ifade olarak kullan.
Suggested veya uncertain etiketleri kesin bilgi gibi yazma.
```

---

## 4.9 Faz 4 kabul kriterleri

- Görseller embedlenebilir.
- Görsellere otomatik caption üretilebilir.
- OCR sonucu alınabilir.
- Admin görselleri etiketleyebilir.
- Entity registry çalışır.
- Benzer görsel önerileri gösterilir.
- İçerik üretiminde verified görsel etiketleri kullanılabilir.

---

# Faz 5 — Stil profili çıkarma ve stil uyarlamalı içerik üretimi

## 5.1 Amaç

Kullanıcı kendi yazı stilini veya beğendiği bir hesabın yazı stilini sisteme tanıtabilmeli. Sistem gündem verisini önce RAG ile bulmalı, sonra içeriği seçilen stile uygun şekilde üretmelidir.

---

## 5.2 Stil kaynakları

```text
Kullanıcının manuel eklediği örnek metinler
Kullanıcının kendi X hesabından izinli içerikler
Beğendiği kamuya açık hesaplardan manuel eklenen örnekler
CSV/JSON import
```

Not: Otomatik X scraping hukuki ve teknik riskler taşıyabilir. İlk MVP’de kullanıcı tarafından sağlanan metin örnekleriyle başlamak daha güvenlidir.

---

## 5.3 Stil profili çıktısı

```json
{
  "style_name": "Analitik ve sade politik yorum",
  "sentence_length": "medium",
  "tone": ["sade", "eleştirel", "kanıta dayalı"],
  "rhetorical_patterns": [
    "Önce güçlü iddia",
    "Sonra veri/kaynak dayanağı",
    "Son cümlede çağrı veya vurucu sonuç"
  ],
  "avoid": [
    "aşırı slogan",
    "uzun akademik cümle",
    "hakaret"
  ],
  "sample_transforms": []
}
```

---

## 5.4 Stil uyarlama akışı

```text
RAG ile gündem verisi bulunur.
↓
Gündem kartları seçilir.
↓
Nötr temel içerik taslağı üretilir.
↓
Stil profili uygulanır.
↓
Stil güvenlik kontrolü yapılır.
↓
Kullanıcıya çıktı verilir.
```

---

## 5.5 Stil güvenlik ilkeleri

- Kullanıcının yazı stili taklit edilebilir.
- Başka bir gerçek kişiyi aldatıcı şekilde birebir impersonate etmekten kaçınılmalıdır.
- Sistem “tam olarak X kişisi yazmış gibi” değil, “şu stil özelliklerine yakın” yaklaşımıyla çalışmalıdır.
- Telifli metinlerden uzun birebir kopya üretmemelidir.

---

## 5.6 Veri modeli

```sql
style_profiles
- id
- user_id
- name
- source_type
- style_summary
- rules_json
- sample_count
- created_at
- updated_at
```

```sql
style_samples
- id
- style_profile_id
- text
- source_url
- created_at
```

---

## 5.7 Faz 5 kabul kriterleri

- Kullanıcı örnek metin girebilir.
- Sistem stil profili çıkarabilir.
- Kullanıcı içerik üretirken stil profili seçebilir.
- Üretilen içerik RAG verisine sadık kalır.
- Stil, veri doğruluğunun önüne geçmez.

---

# Faz 6 — Ücretsiz deneme, paketler ve ödeme sistemi

## 6.1 Amaç

Ürün ücretsiz deneme ve ücretli abonelik modeliyle çalışabilmelidir.

---

## 6.2 Deneme türleri

### Üyeliksiz deneme

```text
IP + browser fingerprint + rate limit
Günlük 1–3 üretim
Düşük model kalitesi
Kaynak görünürlüğü sınırlı
```

### Üyelikli ücretsiz deneme

```text
E-posta ile kayıt
Günlük/aylık sınırlı üretim
Daha iyi sonuç
Geçmiş kayıtları
```

### Ücretli paketler

```text
Daha yüksek üretim limiti
Daha iyi model provider
Daha uzun context
Gelişmiş karşılaştırma
Stil profili
Görsel destekli içerik
```

---

## 6.3 Paket sistemi

```sql
plans
- id
- name
- price
- currency
- monthly_generation_limit
- max_context_cards
- allowed_models
- style_profiles_allowed
- visual_features_allowed
- created_at
```

```sql
subscriptions
- id
- user_id
- plan_id
- status
- current_period_start
- current_period_end
- payment_provider
- provider_subscription_id
```

---

## 6.4 Ödeme sağlayıcı abstraction

Ödeme sistemi de provider bağımsız olmalıdır.

```text
PaymentProvider
- createCheckoutSession()
- handleWebhook()
- cancelSubscription()
- getSubscriptionStatus()
```

İleride kullanılabilecekler:

```text
Stripe
Lemon Squeezy
iyzico
PayTR
Paddle
```

---

## 6.5 Faz 6 kabul kriterleri

- Planlar tanımlanabilir.
- Kullanıcı ücretsiz deneme yapabilir.
- Limitler uygulanır.
- Ücretli kullanıcı farklı quota alır.
- Payment provider adapter mimarisi hazırdır.
- Webhook eventleri işlenir.

---

# Faz 7 — Ölçeklenebilirlik, performans ve operasyon

## 7.1 Amaç

Tek VPS üzerinde başlasa bile sistem binlerce kullanıcıya doğru ölçeklenebilecek şekilde tasarlanmalıdır.

---

## 7.2 Queue stratejisi

### Queue grupları

```text
crawl_queue
media_queue
cleaning_queue
embedding_queue
event_queue
generation_queue
vision_queue
billing_queue
```

### Concurrency

```text
crawl_queue:
- source bazlı rate limit
- domain bazlı concurrency

embedding_queue:
- provider quota’ya göre concurrency

generation_queue:
- user plan’a göre priority

vision_queue:
- düşük priority
- batch çalışabilir
```

### Priority

```text
priority 100: admin test
priority 80: paid user generation
priority 50: free user generation
priority 30: scheduled crawling
priority 10: backfill/archive processing
```

---

## 7.3 Rate limiting

Sistem şu seviyelerde rate limit uygulamalıdır:

```text
IP bazlı
User bazlı
Plan bazlı
Provider bazlı
Source domain bazlı
Queue bazlı
```

---

## 7.4 Caching

### Cache türleri

```text
Query plan cache
Embedding cache
Retrieval result cache
Agenda card cache
Generated answer cache, opsiyonel
Provider response cache, sadece uygun durumlarda
```

### Semantic cache

Benzer kullanıcı taleplerinde aynı gündem kartları yeniden kullanılabilir.

---

## 7.5 Database indeksleri

Önerilen indeksler:

```sql
articles(canonical_url)
articles(content_hash)
articles(published_at)
articles(source_id, published_at)
article_chunks USING ivfflat/hnsw (embedding)
agenda_cards USING ivfflat/hnsw (embedding)
agenda_cards(status, created_at)
event_clusters(status, last_updated_at)
image_embeddings USING ivfflat/hnsw (embedding)
```

---

## 7.6 Bakım işleri

```text
Eski raw HTML snapshot temizliği
Başarısız job temizliği
Duplicate image cleanup
Eski cache temizliği
Embedding provider migration
Gündem kartı yeniden hesaplama
Kaynak healthcheck
Database vacuum/analyze
Yedekleme
```

---

## 7.7 Backup stratejisi

Minimum:

```text
Günlük PostgreSQL dump
Haftalık tam MinIO backup
Günlük config backup
Şifreli off-server backup, mümkünse
```

MVP’de bile yedek zorunludur.

---

## 7.8 Observability

Admin panelde görünmesi gerekenler:

```text
Toplam kaynak sayısı
Aktif kaynak sayısı
Son 24 saatte çekilen haber sayısı
Başarısız kaynak sayısı
Queue uzunlukları
Worker durumları
Provider hata oranları
Embedding bekleyen iş sayısı
Generation bekleyen iş sayısı
Disk kullanımı
DB boyutu
MinIO boyutu
```

---

# 8. Güvenlik ve uyumluluk

## 8.1 Admin güvenliği

- Admin panel 2FA desteklemelidir.
- Admin action log tutulmalıdır.
- Selector/config değişiklikleri versionlanmalıdır.
- API key’ler plaintext tutulmamalıdır.
- Role-based access control uygulanmalıdır.

## 8.2 Kullanıcı güvenliği

- Password hash: Argon2 veya bcrypt
- Session: secure cookie
- CSRF koruması
- Rate limit
- Abuse detection
- Kullanıcı verilerinin izinsiz erişimi engellenmeli

## 8.3 Scraping uyumluluğu

- Kaynakların robots.txt ve kullanım şartları değerlendirilmelidir.
- Aşırı istek atılmamalıdır.
- Kaynak bazlı rate limit uygulanmalıdır.
- Telifli içeriğin tamamı son kullanıcıya yeniden yayınlanmamalıdır.
- Kullanıcıya kaynaklı özet ve türetilmiş içerik sunulmalıdır.

## 8.4 Görsel ve kişi etiketleme

- Otomatik kişi tanıma kesin sonuç gibi sunulmamalıdır.
- Admin onayı olmadan kişi etiketi kesin bilgi olarak kullanılmamalıdır.
- Biyometrik veri işleme riskleri değerlendirilmelidir.
- Görsel etiketleri audit log ile takip edilmelidir.

---

# 9. Prompt ve agent sözleşmeleri

## 9.1 Query Planner prompt contract

Input:

```json
{
  "user_request": "...",
  "current_time": "...",
  "user_locale": "tr-TR"
}
```

Output:

```json
{
  "intent": "current_content_generation | archive_analysis | comparative_content_generation | thread_generation",
  "topic_query": "...",
  "mode": "current | weekly | archive | comparison",
  "timeframes": [],
  "output_type": "x_posts | thread | summary | analysis",
  "tone": "...",
  "constraints": [],
  "needs_sources": true
}
```

Rule:

```text
Planner yalnızca JSON döndürmelidir.
Belirsiz zaman ifadelerini current_time’a göre çözmelidir.
Veri üretmemeli, sadece plan üretmelidir.
```

---

## 9.2 Agenda Card Generator contract

Input:

```json
{
  "event_cluster": {},
  "articles": [],
  "current_time": "..."
}
```

Output:

```json
{
  "title": "...",
  "summary": "...",
  "key_points": [],
  "content_angles": [],
  "timeline": [],
  "source_refs": [],
  "status": "developing | active | cooling | stale",
  "importance_score": 0.0,
  "freshness_score": 0.0
}
```

Rule:

```text
Sadece verilen article verilerini kullan.
Kaynakta olmayan kişi, tarih, kurum, iddia ekleme.
```

---

## 9.3 Content Generator contract

Input:

```json
{
  "request": "...",
  "retrieval_plan": {},
  "agenda_cards": [],
  "style_profile": null,
  "output_constraints": {}
}
```

Output:

```json
{
  "posts": [],
  "summary": "...",
  "sources": [],
  "warnings": []
}
```

Rule:

```text
Sadece verilen gündem kartlarını kullan.
Yetersiz veri varsa warnings içinde bildir.
Eski içeriği güncelmiş gibi sunma.
```

---

# 10. API taslakları

## 10.1 Admin kaynak API

```http
POST /admin/sources
GET /admin/sources
GET /admin/sources/{id}
PATCH /admin/sources/{id}
POST /admin/sources/{id}/test-listing
POST /admin/sources/{id}/test-detail
POST /admin/sources/{id}/crawl-now
GET /admin/sources/{id}/health
```

## 10.2 Haber API

```http
GET /admin/articles
GET /admin/articles/{id}
POST /admin/articles/{id}/reprocess
GET /admin/articles/{id}/images
```

## 10.3 RAG API

```http
POST /internal/rag/plan
POST /internal/rag/retrieve
POST /internal/rag/generate-card
POST /internal/rag/generate-content
```

## 10.4 Kullanıcı API

```http
POST /app/generate
GET /app/generations
GET /app/generations/{id}
POST /app/style-profiles
GET /app/style-profiles
```

## 10.5 Görsel API

```http
GET /admin/images
GET /admin/images/{id}
POST /admin/images/{id}/analyze
POST /admin/images/{id}/labels
PATCH /admin/image-labels/{id}
GET /admin/entities
POST /admin/entities
```

---

# 11. Geliştirme öncelik sırası

## MVP-1

```text
Faz 0
Faz 1 temel RSS + kategori kaynak ekleme
Haber detay kazıma
Temizleme
Görsel arşivleme
Queue sistemi
```

## MVP-2

```text
Chunking
Embedding
Semantic search
Agenda card
Current mode içerik üretimi
```

## MVP-3

```text
Kullanıcı dashboard
X post üretimi
Kaynaklı çıktı
Kullanım limiti
```

## MVP-4

```text
Comparison mode
Archive mode
Weekly summary
```

## MVP-5

```text
Görsel analiz
Admin görsel etiketleme
Görsel RAG
```

## MVP-6

```text
Stil profili
Ücretli paket
Ödeme sistemi
```

---

# 12. Riskler ve önlemler

## 12.1 Haber kazıma kırılganlığı

Risk:

```text
Kaynak HTML yapısı değişebilir.
```

Önlem:

```text
Selector test ekranı
Source health monitoring
Fallback extractor
Admin uyarıları
Config versioning
```

## 12.2 Model maliyeti

Risk:

```text
Her haber için LLM çağrısı maliyeti artırır.
```

Önlem:

```text
LLM’i sadece agenda card ve generation aşamasında kullan.
Embedding cache kullan.
Batch processing kullan.
Trial kullanıcıları ucuz provider’a yönlendir.
```

## 12.3 Eski veriyle güncel veri karışması

Risk:

```text
Model eski haberi güncelmiş gibi kullanabilir.
```

Önlem:

```text
Zaman filtreli retrieval
Agenda card status
Freshness score
Prompt içinde tarih kuralı
Veri yeterliliği kontrolü
```

## 12.4 Telif riski

Risk:

```text
Haberlerin tam metninin kullanıcıya yeniden yayınlanması.
```

Önlem:

```text
Tam haber metni yerine özet/kaynaklı türetilmiş içerik
Kaynak linkleri
İç kullanım ve RAG context ayrımı
```

## 12.5 Görsel kişi tanıma riski

Risk:

```text
Yanlış kişi etiketi veya biyometrik veri riski.
```

Önlem:

```text
Admin onayı
Suggested/verified ayrımı
Kesin otomatik kişi iddiası yok
Audit log
```

## 12.6 Tek VPS ölçek limiti

Risk:

```text
Tüm servisler tek sunucuda darboğaz yaşayabilir.
```

Önlem:

```text
Queue tabanlı mimari
Worker sayısı artırılabilir
Storage ayrıştırılabilir
Provider çağrıları rate limited
DB indeksleri optimize edilir
İleride servisler ayrı VPS’lere taşınabilir
```

---

# 13. Başarı metrikleri

## 13.1 Teknik metrikler

```text
Kaynak başına başarılı crawl oranı
Haber extraction confidence ortalaması
Duplicate oranı
Embedding başarısızlık oranı
Generation başarısızlık oranı
Ortalama generation süresi
Queue bekleme süresi
Provider hata oranı
Disk büyüme hızı
```

## 13.2 Ürün metrikleri

```text
Günlük aktif kullanıcı
Kullanıcı başına üretim sayısı
Üretilen içerik kaydetme oranı
Tekrar üretim oranı
Kaynaklı çıktı görüntüleme oranı
Trial → üyelik dönüşümü
Üyelik → ücretli dönüşüm
```

## 13.3 Kalite metrikleri

```text
Veri yetersizliği doğru tespit oranı
Yanlış kaynak kullanımı oranı
Eski haberi güncel sanma oranı
Admin düzeltme ihtiyacı
Kullanıcı beğeni/yeniden üretme sinyali
```

---

# 14. Nihai ürün davranışı

Sistem şu şekilde davranmalıdır:

```text
Admin kaynakları belirler.
Sistem haberleri toplar.
Sistem metinleri temizler.
Sistem görselleri arşivler.
Sistem haberleri RAG hafızasına alır.
Sistem benzer haberleri olaylara gruplar.
Sistem güncel gündem kartları oluşturur.
Kullanıcı istediği gündemi yazar.
Sistem isteğin zaman modunu anlar.
Sistem sadece alakalı ve yeterli veriyi getirir.
Sistem kaynaklı ve güvenilir içerik üretir.
Veri yoksa uydurmaz.
Eski veri gerekiyorsa arşiv moduna geçer.
Karşılaştırma gerekiyorsa her dönemi ayrı işler.
Görsel gerekiyorsa yalnızca doğrulanmış görsel etiketlerini kullanır.
```

---

# 15. Yapay zeka ajanı için uygulanabilir görev listesi

## Agent Task Group A — Infrastructure

```text
A1. Docker Compose dosyasını oluştur.
A2. PostgreSQL + pgvector kurulumunu ekle.
A3. Redis servisini ekle.
A4. MinIO servisini ekle.
A5. API healthcheck endpoint’i yaz.
A6. Worker healthcheck sistemi kur.
A7. Environment config loader yaz.
```

## Agent Task Group B — Source Management

```text
B1. sources tablosunu oluştur.
B2. source_configs tablosunu oluştur.
B3. Admin source create/update endpointlerini yaz.
B4. RSS parser servis modülünü yaz.
B5. Category listing fetcher modülünü yaz.
B6. Selector test endpoint’i yaz.
B7. Detail page extractor modülünü yaz.
B8. Source health monitor yaz.
```

## Agent Task Group C — Article Pipeline

```text
C1. articles tablosunu oluştur.
C2. Raw HTML snapshot storage yaz.
C3. Clean text extractor yaz.
C4. URL canonicalizer yaz.
C5. Content hash/dedupe modülünü yaz.
C6. Language detection ekle.
C7. Article status state machine yaz.
```

## Agent Task Group D — Media Pipeline

```text
D1. article_images tablosunu oluştur.
D2. Image downloader worker yaz.
D3. Image hash/perceptual hash üret.
D4. MinIO image storage yaz.
D5. Duplicate image detection ekle.
```

## Agent Task Group E — RAG

```text
E1. article_chunks tablosunu oluştur.
E2. Chunker modülünü yaz.
E3. Model provider interface yaz.
E4. Nvidia NIM adapter yaz.
E5. Embedding worker yaz.
E6. pgvector search fonksiyonunu yaz.
E7. event_clusters tablosunu oluştur.
E8. Event clustering modülünü yaz.
E9. agenda_cards tablosunu oluştur.
E10. Agenda card generator yaz.
```

## Agent Task Group F — User Generation

```text
F1. Query Planner yaz.
F2. Retrieval mode resolver yaz.
F3. Current mode retrieval yaz.
F4. Archive mode retrieval yaz.
F5. Comparison mode retrieval yaz.
F6. Data sufficiency checker yaz.
F7. Content generation prompt contract yaz.
F8. generations tablosunu oluştur.
F9. User dashboard generate endpoint’i yaz.
```

## Agent Task Group G — Visual Intelligence

```text
G1. image_analysis tablosunu oluştur.
G2. image_embeddings tablosunu oluştur.
G3. Image VLM adapter yaz.
G4. OCR pipeline ekle.
G5. Entity registry oluştur.
G6. image_labels tablosunu oluştur.
G7. Admin labeling UI tasarla.
G8. Similar image suggestion ekle.
```

## Agent Task Group H — Style Clone

```text
H1. style_profiles tablosunu oluştur.
H2. style_samples tablosunu oluştur.
H3. Style analyzer prompt yaz.
H4. Style application pipeline yaz.
H5. Style safety rules ekle.
```

## Agent Task Group I — Billing

```text
I1. plans tablosunu oluştur.
I2. subscriptions tablosunu oluştur.
I3. usage_events tablosunu oluştur.
I4. Trial limit middleware yaz.
I5. PaymentProvider interface yaz.
I6. İlk ödeme sağlayıcı adapter’ını ekle.
```

---

# 16. MVP için önerilen ilk teknik hedef

İlk çalışan MVP şu tek senaryoyu kusursuz yapmalıdır:

```text
Admin 3 haber kaynağı ekler.
Sistem son 24 saatteki haberleri toplar.
Haberleri temizler.
Görselleri arşivler.
Haberleri chunk’lar ve embedler.
Benzer haberleri gündem kartlarına dönüştürür.
Kullanıcı “bugünkü ekonomi gündemiyle 5 X paylaşımı üret” der.
Sistem ilgili gündem kartlarını getirir.
Model kaynaklı 5 paylaşım üretir.
Veri yoksa bunu açıkça söyler.
```

Bu senaryo sağlıklı çalışmadan stil klonlama, ödeme ve gelişmiş görsel zeka fazlarına geçilmemelidir.

---

# 17. Son mimari karar

Bu ürünün temel mimari kararı şudur:

```text
LLM’e tüm interneti veya tüm haber arşivini okutma.
Haberleri senin kontrolündeki güvenilir havuzda topla.
Haberleri olay kartlarına dönüştür.
Kullanıcının doğal dil talebini zaman ve niyet planına çevir.
Modele sadece seçilmiş, güncel, kaynaklı ve yeterli bağlamı ver.
```

Bu yaklaşım hem maliyeti düşürür hem güvenilirliği artırır hem de SaaS olarak ölçeklenebilir bir ürün mimarisi sağlar.

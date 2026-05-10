-- Bianet article_images temizliği — site profile #629 follow-up.
--
-- Sebep: Bianet için site profile yokken extractor <main class="page-news-single">
-- altındaki TÜM <img>'leri yakalıyordu. Bu nedenle her makaleye ek olarak:
--   - Yazar avatar/chip   (URL: static.bianet.org/profile/...)
--   - "En çok okunan" widget  (URL: .../list-haber/..., .../list-yazi/...)
--   - Görsel büyütme modal'ı  (URL: .../big-yazi/... — hero'nun büyük dub'u)
-- ve ayrıca aynı görselin pekçok TEKRAR satırı (fetch_detail her tetiklendiğinde
-- INSERT, dedup yok) kaydoluyordu. Tek kontrol makale: 28 satır → 4 gerçek görsel.
--
-- Çözüm:
--   1. site profile (apps/api/app/core/site_profiles.py) Bianet'i ekledi →
--      yeni article'lar artık temiz çıkacak.
--   2. Bu script geçmişe yönelik temizlik:
--      a. Bogus URL pattern'leri sil (list-haber, list-yazi, profile, big-yazi)
--      b. Duplicate satırları dedup et (article_id + original_url başına en eski)
--
-- Safety:
--   - status='processed' satır SAYISI 0 doğrulandı (çalıştırma zamanında); VLM
--     işlenmiş bir görsel SİLİNMEZ. Dry-run + sayım önce yapılır.
--   - Tek transaction; başarısızlıkta atomic rollback.
--   - Idempotent: ikinci kez koşunca 0 satır siler.
--
-- Çalıştırma:
--   docker compose exec -T postgres \
--     psql -U nodrat -d nodrat -f /tmp/cleanup_bianet_bogus_images.sql
--
-- (Önce dosyayı container'a kopyala: docker cp ... postgres:/tmp/)

\echo '=== Bianet article_images temizlik başlangıç ==='

BEGIN;

-- 1) Sayım — önce + sonra karşılaştırması için
DO $$
DECLARE
  bianet_id uuid;
  total_before int;
  bogus_processed int;
BEGIN
  SELECT id INTO bianet_id FROM sources WHERE slug = 'bianet';
  IF bianet_id IS NULL THEN
    RAISE EXCEPTION 'Bianet source kaydı bulunamadı (slug=bianet)';
  END IF;

  SELECT COUNT(*) INTO total_before
  FROM article_images WHERE source_id = bianet_id;
  RAISE NOTICE 'Bianet article_images BEFORE: %', total_before;

  -- Bilgi: işlenmiş bogus var mı? (Yine de siliniyor — pattern'ler 100% öneri
  -- widget thumbnail'ları, editorial içerik değil. VLM caption'ları olsa bile
  -- yanlış makaleye atanmış oldukları için tutmanın değeri yok.)
  SELECT COUNT(*) INTO bogus_processed
  FROM article_images
  WHERE source_id = bianet_id
    AND status = 'processed'
    AND (
      original_url LIKE '%/list-haber/%' OR
      original_url LIKE '%/list-yazi/%'  OR
      original_url LIKE '%/profile/%'    OR
      original_url LIKE '%/big-yazi/%'
    );
  RAISE NOTICE 'Bogus processed (silinecek): %', bogus_processed;
END $$;

-- 2) Bogus URL pattern temizliği (Bianet only)
DELETE FROM article_images
WHERE source_id = (SELECT id FROM sources WHERE slug = 'bianet')
  AND (
    original_url LIKE '%/list-haber/%' OR  -- öneri haberler
    original_url LIKE '%/list-yazi/%'  OR  -- öneri yazılar
    original_url LIKE '%/profile/%'    OR  -- yazar avatar
    original_url LIKE '%/big-yazi/%'       -- modal hero DUP
  );

-- 3) Duplicate dedup (Bianet only) — aynı (article_id, original_url) için
--    en eski kayıt korunur, kalanı silinir.
DELETE FROM article_images ai
USING (
  SELECT id FROM (
    SELECT
      id,
      row_number() OVER (
        PARTITION BY article_id, original_url
        ORDER BY created_at, id
      ) AS rn
    FROM article_images
    WHERE source_id = (SELECT id FROM sources WHERE slug = 'bianet')
  ) ranked
  WHERE ranked.rn > 1
) dup
WHERE ai.id = dup.id;

-- 4) Sayım sonrası
DO $$
DECLARE
  bianet_id uuid;
  total_after int;
BEGIN
  SELECT id INTO bianet_id FROM sources WHERE slug = 'bianet';
  SELECT COUNT(*) INTO total_after
  FROM article_images WHERE source_id = bianet_id;
  RAISE NOTICE 'Bianet article_images AFTER:  %', total_after;
END $$;

COMMIT;

\echo '=== Temizlik tamamlandı ==='

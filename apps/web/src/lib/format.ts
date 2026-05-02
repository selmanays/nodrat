/**
 * Tarih formatlamak için Türkiye saatine sabitlenmiş yardımcılar (#232).
 *
 * `toLocaleString("tr-TR")` browser'ın varsayılan timezone'una göre çalışır;
 * kullanıcı yurt dışındaysa UTC veya farklı saat görür. Bu helper'lar
 * `Europe/Istanbul` ile sabitler — sunucu hangi UTC ISO döndürürse döndürsün
 * UI tutarlı şekilde TR saati gösterir.
 */

const ISTANBUL = "Europe/Istanbul";

function _safeDate(value: string | Date | null | undefined): Date | null {
  if (value == null) return null;
  const d = value instanceof Date ? value : new Date(value);
  if (isNaN(d.getTime())) return null;
  return d;
}

/**
 * "2 May 2026 21:06" — günlük özetler, kart altyazıları için.
 */
export function formatTrDate(
  value: string | Date | null | undefined,
  fallback = "—",
): string {
  const d = _safeDate(value);
  if (!d) return fallback;
  return d.toLocaleString("tr-TR", {
    timeZone: ISTANBUL,
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * "2 Mayıs 2026 21:06:09" — admin tabloları, audit log, detay sayfaları.
 */
export function formatTrDateTime(
  value: string | Date | null | undefined,
  fallback = "—",
): string {
  const d = _safeDate(value);
  if (!d) return fallback;
  return d.toLocaleString("tr-TR", {
    timeZone: ISTANBUL,
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/**
 * "2.05.2026" — sadece gün, üye listesi gibi yerler.
 */
export function formatTrDateOnly(
  value: string | Date | null | undefined,
  fallback = "—",
): string {
  const d = _safeDate(value);
  if (!d) return fallback;
  return d.toLocaleDateString("tr-TR", {
    timeZone: ISTANBUL,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

/**
 * Şu andan farkı: "5 dk önce", "2 sa önce", "dün", "5 May".
 * Yakın zaman için relative, eski tarihler için kısa absolute.
 */
export function formatRelativeTr(
  value: string | Date | null | undefined,
  fallback = "—",
): string {
  const d = _safeDate(value);
  if (!d) return fallback;
  const diffSec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (diffSec < 60) return "az önce";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} dk önce`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} sa önce`;
  if (diffSec < 172800) return "dün";
  if (diffSec < 604800)
    return `${Math.floor(diffSec / 86400)} gün önce`;
  return formatTrDate(d);
}

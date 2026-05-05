/**
 * Sistem ayarları grup metadata — sidebar nav, route mapping ve grup label'ları
 * burada merkezi olarak tutulur.
 */

export const SETTINGS_GROUPS = [
  { slug: "rag", label: "RAG / Yeniden Sıralama" },
  { slug: "retrieval", label: "Hibrit Retrieval" },
  { slug: "clustering", label: "Olay Kümeleme" },
  { slug: "chunker", label: "Chunker" },
  { slug: "media", label: "Görsel İndirme" },
  { slug: "quota", label: "Kota & Limitler" },
  { slug: "scraping", label: "Kazıma Politikası" },
  { slug: "llm", label: "LLM Modelleri" },
  { slug: "auth", label: "Auth / JWT" },
  { slug: "cost", label: "Maliyet Cap'leri" },
  { slug: "schedule", label: "Worker Beat Schedule" },
] as const;

export type SettingsGroupSlug = (typeof SETTINGS_GROUPS)[number]["slug"];

export function getSettingsGroupLabel(slug: string): string {
  return SETTINGS_GROUPS.find((g) => g.slug === slug)?.label ?? slug;
}

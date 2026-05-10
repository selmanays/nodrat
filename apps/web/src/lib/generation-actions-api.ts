/**
 * Generation user-action telemetry API client (#566 SFT telemetry).
 *
 * Backend endpoints (PR #584 production'da):
 *   POST   /app/generations/{id}/copied         — copy-to-clipboard sinyali
 *   POST   /app/generations/{id}/posted         — X / başka platforma paylaşıldı
 *   POST   /app/generations/{id}/edited         — düzenleme (DPO için)
 *   POST   /app/generations/{id}/regenerated    — yeniden üret (negatif sinyal)
 *   DELETE /app/generations/{id}                — sil (negatif sinyal)
 *
 * Tüm çağrılar fire-and-forget (UI'i bloklamaz). Hata sessizce log'lanır.
 *
 * Trendyol-LLM-7B-chat-v4.1.0 üzerine domain-spesifik fine-tune için
 * altın etiketleme sinyalleri.
 */

import { apiFetch } from "@/lib/api";

export interface GenerationEditedResponse {
  status: "edited";
  edit_distance: number | null;
  sft_eligible: boolean;
  sft_excluded_reason: string | null;
}

export async function markGenerationCopied(generationId: string): Promise<void> {
  await apiFetch(`/app/generations/${generationId}/copied`, { method: "POST" });
}

export async function markGenerationPosted(generationId: string): Promise<void> {
  await apiFetch(`/app/generations/${generationId}/posted`, { method: "POST" });
}

export async function markGenerationEdited(
  generationId: string,
  editedText: string,
): Promise<GenerationEditedResponse> {
  return apiFetch<GenerationEditedResponse>(
    `/app/generations/${generationId}/edited`,
    {
      method: "POST",
      body: { edited_text: editedText },
    },
  );
}

export async function markGenerationRegenerated(
  generationId: string,
): Promise<void> {
  await apiFetch(`/app/generations/${generationId}/regenerated`, {
    method: "POST",
  });
}

export async function deleteGeneration(generationId: string): Promise<void> {
  await apiFetch(`/app/generations/${generationId}`, { method: "DELETE" });
}

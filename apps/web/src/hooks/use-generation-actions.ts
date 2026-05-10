/**
 * useGenerationActions hook — SFT telemetry user actions (#566/#568).
 *
 * Generation card'ında copy/post/edit/regenerate/delete butonlarına bağlanır.
 * Tüm callback'ler fire-and-forget — UI'yi bloklamaz, hata sessizce log'lanır.
 *
 * Kullanım:
 *   const { copy, post, edit, regenerate, deleteGen } = useGenerationActions(genId);
 *   <Button onClick={() => copy(text)}>Kopyala</Button>
 *
 * Backend yan etkisi: her action sonrası `_recompute_sft_eligibility` helper
 * generations.sft_eligible flag'ini günceller (KVKK consent + 6 başka koşul).
 */

import { useCallback } from "react";

import {
  deleteGeneration,
  markGenerationCopied,
  markGenerationEdited,
  markGenerationPosted,
  markGenerationRegenerated,
  type GenerationEditedResponse,
} from "@/lib/generation-actions-api";

export interface UseGenerationActions {
  /** Copy-to-clipboard sinyali (text'i ayrıca clipboard'a yazılır). */
  copy: (text: string) => Promise<void>;
  /** X / başka platforma paylaşıldı sinyali. */
  post: () => Promise<void>;
  /** Kullanıcı düzenledi — edit_distance hesaplanır + sft_eligible recompute. */
  edit: (editedText: string) => Promise<GenerationEditedResponse | null>;
  /** Yeniden üret (negatif sinyal). */
  regenerate: () => Promise<void>;
  /** Soft delete sinyali (row korunur, user_action='deleted'). */
  deleteGen: () => Promise<void>;
}

/**
 * Fire-and-forget wrapper — telemetry hatasını UI'den izole eder.
 */
async function silent<T>(fn: () => Promise<T>): Promise<T | null> {
  try {
    return await fn();
  } catch (err) {
    if (typeof console !== "undefined") {
      console.warn("generation-action telemetry failed:", err);
    }
    return null;
  }
}

export function useGenerationActions(generationId: string): UseGenerationActions {
  const copy = useCallback(
    async (text: string) => {
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        // Clipboard API fail (HTTPS dışı dev veya permission denied) — telemetry yine atılır.
      }
      await silent(() => markGenerationCopied(generationId));
    },
    [generationId],
  );

  const post = useCallback(async () => {
    await silent(() => markGenerationPosted(generationId));
  }, [generationId]);

  const edit = useCallback(
    async (editedText: string) => {
      return silent(() => markGenerationEdited(generationId, editedText));
    },
    [generationId],
  );

  const regenerate = useCallback(async () => {
    await silent(() => markGenerationRegenerated(generationId));
  }, [generationId]);

  const deleteGen = useCallback(async () => {
    await silent(() => deleteGeneration(generationId));
  }, [generationId]);

  return { copy, post, edit, regenerate, deleteGen };
}

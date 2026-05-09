/**
 * useGenerationStream — `/app/generate-stream` SSE consumer (#527).
 *
 * Stream event'lerini yerel state'e yansıtır:
 *   - meta → generation_id + plan
 *   - progress → stage label
 *   - chunk → live preview text accumulator
 *   - post → posts array'i progressive olarak doldur
 *   - parsed → final structured (posts/summary/sources tam değerleri)
 *   - citation → repaired post text + warnings
 *   - image → suggested_image
 *   - done → status, cost, ttfb_ms
 *   - error → error state
 *
 * UI render: posts hem "post" event'inden ön-cevap olarak görünür hem
 * de "parsed" event'inden citation-applied final hâliyle değişir.
 */

import { useCallback, useState } from "react";

import {
  generateStream,
  type GenerateRequest,
  type GenerateStreamHandlers,
  type GenerateMode,
  type SuggestedImagePublic,
} from "@/lib/api";

export type StreamStage =
  | "idle"
  | "planning"
  | "retrieving"
  | "generating"
  | "validating"
  | "done"
  | "error";

export interface StreamPost {
  index: number;
  text: string;
  angle: string;
  char_count: number;
  related_agenda_card_ids: string[];
}

export interface StreamSource {
  title: string;
  source: string;
  url: string;
}

export interface StreamSummaryItem {
  event: string;
  source: string;
  date: string;
  agenda_card_id: string | null;
}

export interface StreamErrorState {
  code: string;
  title: string;
  reason: string;
  suggestions?: string[];
}

export interface UseGenerationStreamState {
  stage: StreamStage;
  generationId: string | null;
  mode: GenerateMode | "comparison" | null;
  outputType: string | null;
  tone: string | null;
  topicQuery: string | null;
  posts: StreamPost[];
  summary: string;
  summaryDocTitle: string;
  summaryDocItems: StreamSummaryItem[];
  sources: StreamSource[];
  warnings: string[];
  suggestedImage: SuggestedImagePublic | null;
  rawAccumulator: string; // for live preview before "post" arrives
  costUsd: number | null;
  ttfbMs: number | null;
  error: StreamErrorState | null;
  isStreaming: boolean;
  startedAt: number | null;
  firstByteAt: number | null;
}

const INITIAL_STATE: UseGenerationStreamState = {
  stage: "idle",
  generationId: null,
  mode: null,
  outputType: null,
  tone: null,
  topicQuery: null,
  posts: [],
  summary: "",
  summaryDocTitle: "",
  summaryDocItems: [],
  sources: [],
  warnings: [],
  suggestedImage: null,
  rawAccumulator: "",
  costUsd: null,
  ttfbMs: null,
  error: null,
  isStreaming: false,
  startedAt: null,
  firstByteAt: null,
};

export function useGenerationStream() {
  const [state, setState] = useState<UseGenerationStreamState>(INITIAL_STATE);

  const reset = useCallback(() => setState(INITIAL_STATE), []);

  const start = useCallback(
    async (
      payload: GenerateRequest,
      options: { signal?: AbortSignal } = {},
    ) => {
      const startedAt = performance.now();
      setState({
        ...INITIAL_STATE,
        isStreaming: true,
        stage: "planning",
        startedAt,
      });

      const handlers: GenerateStreamHandlers = {
        onMeta: (data) => {
          setState((prev) => ({
            ...prev,
            generationId: data.generation_id,
            mode: data.mode as UseGenerationStreamState["mode"],
            outputType: data.output_type,
            tone: data.tone,
            topicQuery: data.plan.topic_query,
          }));
        },
        onProgress: (data) => {
          const stage = data.stage as StreamStage;
          if (
            stage === "planning" ||
            stage === "retrieving" ||
            stage === "generating" ||
            stage === "validating"
          ) {
            setState((prev) => ({ ...prev, stage }));
          }
        },
        onChunk: (data) => {
          setState((prev) => ({
            ...prev,
            rawAccumulator: prev.rawAccumulator + data.delta,
            firstByteAt: prev.firstByteAt ?? performance.now(),
          }));
        },
        onPost: (data) => {
          setState((prev) => {
            const posts = [...prev.posts];
            const existing = posts.findIndex((p) => p.index === data.index);
            if (existing >= 0) {
              posts[existing] = data;
            } else {
              posts.push(data);
              posts.sort((a, b) => a.index - b.index);
            }
            return { ...prev, posts };
          });
        },
        onParsed: (data) => {
          setState((prev) => ({
            ...prev,
            posts: data.posts.map((p, i) => ({
              index: i,
              text: p.text,
              angle: p.angle,
              char_count: p.char_count,
              related_agenda_card_ids: p.related_agenda_card_ids,
            })),
            summary: data.summary,
            summaryDocTitle: data.summary_doc_title,
            summaryDocItems: data.summary_doc_items,
            sources: data.sources,
            warnings: data.warnings,
          }));
        },
        onCitation: (data) => {
          // Citation repair'lardan gelen metni post text'e uygula
          setState((prev) => {
            const posts = [...prev.posts];
            for (const r of data.posts_after_repair) {
              const i = posts.findIndex((p) => p.index === r.index);
              if (i >= 0) {
                posts[i] = {
                  ...posts[i],
                  text: r.text,
                  char_count: r.char_count,
                };
              }
            }
            return {
              ...prev,
              posts,
              warnings: [...prev.warnings, ...data.unsupported_warnings],
            };
          });
        },
        onImage: (data) => {
          setState((prev) => ({
            ...prev,
            suggestedImage: {
              image_id: data.image_id,
              article_id: data.article_id,
              original_url: data.original_url,
              vlm_caption: data.vlm_caption,
              depicts: data.depicts,
              alt_text: data.alt_text,
              score: data.score,
              reason: data.reason,
            },
          }));
        },
        onDone: (data) => {
          setState((prev) => ({
            ...prev,
            stage: "done",
            isStreaming: false,
            costUsd: data.cost_usd ?? prev.costUsd,
            ttfbMs: data.ttfb_ms ?? prev.ttfbMs,
          }));
        },
        onError: (data) => {
          setState((prev) => ({
            ...prev,
            stage: "error",
            isStreaming: false,
            error: {
              code: data.code,
              title: data.title,
              reason: data.reason,
              suggestions: data.suggestions,
            },
          }));
        },
      };

      try {
        await generateStream(payload, handlers, options);
      } catch (err) {
        const e = err as Error;
        setState((prev) => ({
          ...prev,
          stage: "error",
          isStreaming: false,
          error: {
            code: "FETCH_ERROR",
            title: "Bağlantı hatası",
            reason: e.message || "Bilinmeyen hata",
          },
        }));
      }
    },
    [],
  );

  return { state, start, reset };
}

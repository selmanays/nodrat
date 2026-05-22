/**
 * Research API client — Perplexity-style conversation mode (#793), non-SSE side.
 *
 * Extracted from `api.ts` (Research section) in T6 P7a PR-7a-19a (Part 1 of 2).
 * The SSE streaming function `streamResearchMessage` stays INLINE in `api.ts`
 * (raw fetch + module-local `API_BASE` coupling) → Part 2/2 (PR-7a-19b).
 *
 * Primary callers (5):
 *   - apps/web/src/app/app/research/page.tsx
 *   - apps/web/src/app/app/research/[id]/page.tsx
 *   - apps/web/src/components/research/MessageActions.tsx
 *   - apps/web/src/components/research/HaluFlagModal.tsx
 *   - apps/web/src/components/research/ConversationSidebar.tsx
 *
 * Backend endpoints:
 *   - GET    /research/conversations{?q}        — listResearchConversations (read-only)
 *   - POST   /research/conversations            — createResearchConversation
 *   - GET    /research/conversations/{id}       — getResearchConversation (read-only)
 *   - PATCH  /research/conversations/{id}       — renameResearchConversation (0-caller, korundu)
 *   - DELETE /research/conversations/{id}       — archiveResearchConversation
 *   - POST   /research/messages/{id}/flag-halu  — flagResearchMessageHalu
 *   - POST   /research/messages/{id}/action     — recordResearchMessageAction
 *
 * Backward-compat: `api.ts` re-exports these symbols → `@/lib/api` caller
 * import path DEĞİŞMEZ.
 *
 * Dependencies (core, NOT extracted):
 * - apiFetch   — core HTTP helper (../api)
 * - buildQuery — shared query-string helper (./_query)
 */

import { apiFetch } from "../api";
import { buildQuery } from "./_query";

export interface ResearchConversationItem {
  id: string;
  title: string;
  summary?: string | null;
  message_count: number;
  last_answer_snippet?: string | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface ResearchConversationList {
  items: ResearchConversationItem[];
  total: number;
}

export interface ResearchMessageSource {
  // #813 Faz 2 2B — source_type ile "haber" vs "wikipedia" ayrımı.
  source_type?: "news" | "wikipedia";
  article_id?: string;
  chunk_id?: string;
  title?: string;
  url?: string;
  source_name?: string;
  license?: string;          // CC BY-SA 4.0 (Wikipedia) gibi
  cite?: string;             // #845 — bu kaynağın citation token'ı ([3]/[W1])
}

export interface ResearchMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources_used?: ResearchMessageSource[] | null;
  sources_considered?: ResearchMessageSource[] | null;
  thinking_steps?: Array<{
    phase: string;
    detail?: string;
    latency_ms?: number;
    // Faza göre değişen opsiyonel alanlar (planner/confidence/tool_use)
    type?: string;
    topic_query?: string;
    confidence_score?: number;
    missing_signals?: string[];
    source_type?: string;
    article_count?: number;
  }> | null;
  followup_suggestions?: string[] | null; // #961
  // S1C feedback fields
  halu_flagged_at?: string | null;
  user_action?: string | null;
  user_action_at?: string | null;
  sft_eligible?: boolean;
  dpo_rejected?: boolean;
  created_at: string;
}

export interface ResearchThread {
  id: string;
  title: string;
  summary?: string | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
  messages: ResearchMessage[];
}

export async function listResearchConversations(opts?: {
  include_archived?: boolean;
  limit?: number;
  offset?: number;
}): Promise<ResearchConversationList> {
  return apiFetch<ResearchConversationList>(
    `/research/conversations${buildQuery(opts as Record<string, unknown> | undefined)}`,
  );
}

export async function createResearchConversation(
  title?: string,
): Promise<ResearchConversationItem> {
  return apiFetch<ResearchConversationItem>("/research/conversations", {
    method: "POST",
    body: { title: title || null },
  });
}

export async function getResearchConversation(id: string): Promise<ResearchThread> {
  return apiFetch<ResearchThread>(`/research/conversations/${id}`);
}

export async function renameResearchConversation(
  id: string,
  title: string,
): Promise<ResearchConversationItem> {
  return apiFetch<ResearchConversationItem>(`/research/conversations/${id}`, {
    method: "PATCH",
    body: { title },
  });
}

export async function archiveResearchConversation(id: string): Promise<void> {
  return apiFetch(`/research/conversations/${id}`, { method: "DELETE" });
}

// ---- Message feedback (#802 S1C) ----

export interface MessageFeedbackResponse {
  id: string;
  halu_flagged_at: string | null;
  user_action: string | null;
  user_action_at: string | null;
  sft_eligible: boolean;
  sft_excluded_reason: string | null;
  dpo_rejected: boolean;
}

export async function flagResearchMessageHalu(
  msgId: string,
  reason?: string | null,
  chosenContent?: string | null,
): Promise<MessageFeedbackResponse> {
  return apiFetch<MessageFeedbackResponse>(
    `/research/messages/${msgId}/flag-halu`,
    {
      method: "POST",
      body: { reason: reason || null, chosen_content: chosenContent || null },
    },
  );
}

export async function recordResearchMessageAction(
  msgId: string,
  action: "copied" | "posted" | "edited" | "none",
  opts?: { edit_distance?: number; edited_content?: string | null },
): Promise<MessageFeedbackResponse> {
  return apiFetch<MessageFeedbackResponse>(
    `/research/messages/${msgId}/action`,
    {
      method: "POST",
      body: {
        action,
        edit_distance: opts?.edit_distance,
        edited_content: opts?.edited_content,
      },
    },
  );
}

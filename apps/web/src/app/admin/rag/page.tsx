"use client";

/**
 * Admin RAG Observability — Türkçe arayüz + tooltip'li kısaltmalar (#194)
 *
 * Epic #189 — sistem yöneticisi paneli RAG izleme.
 * Sekmeler: Sağlık / Karşılaştırma / Atıf / Yeniden Sıralama / RAPTOR / İnceleyici
 */

import { useState } from "react";

import { PageHeader } from "@/components/blocks/page-header";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

import { BenchmarkTab } from "./_tabs/benchmark";
import { CacheTab } from "./_tabs/cache";
import { CitationTab } from "./_tabs/citation";
import { HealthTab } from "./_tabs/health";
import { InspectorTab } from "./_tabs/inspector";
import { NerTab } from "./_tabs/ner";
import { PerformanceTab } from "./_tabs/performance";
import { RaptorTab } from "./_tabs/raptor";
import { RerankTab } from "./_tabs/rerank";

// ============================================================================
// Sayfa tipi + thin router
// ============================================================================
//
// Phase 7b admin/rag mini-plan TAMAMLANDI:
//   HINTS/StatCard/KV/fmt → ./_shared.tsx (PR-7b-1)
//   Tab fonksiyonları → ./_tabs/*.tsx (PR-7b-2..PR-7b-10)
// Bu dosya artık SADECE root router (TabKey + TABS + AdminRagPage).

type TabKey =
  | "health"
  | "benchmark"
  | "citation"
  | "rerank"
  | "ner"
  | "raptor"
  | "inspector"
  | "performance"
  | "cache";

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: "health", label: "Sağlık" },
  { key: "benchmark", label: "Karşılaştırma" },
  { key: "citation", label: "Atıf" },
  { key: "rerank", label: "Yeniden Sıralama" },
  { key: "ner", label: "NER" },  // #696 B5
  { key: "raptor", label: "RAPTOR" },
  { key: "inspector", label: "İnceleyici" },
  { key: "performance", label: "Performans" },
  { key: "cache", label: "Önbellek" },
];

export default function AdminRagPage() {
  const [tab, setTab] = useState<TabKey>("health");

  return (
    <div className="space-y-6">
      <PageHeader
        title="RAG İzlencesi"
        description="Değerlendirme, atıf, yeniden sıralama ve RAPTOR-Lite katmanlarının durumunu izleyin."
      />

      <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
        <TabsList aria-label="RAG sekmeleri">
          {TABS.map(({ key, label }) => (
            <TabsTrigger key={key} value={key}>
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="health" className="mt-4">
          <HealthTab />
        </TabsContent>
        <TabsContent value="benchmark" className="mt-4">
          <BenchmarkTab />
        </TabsContent>
        <TabsContent value="citation" className="mt-4">
          <CitationTab />
        </TabsContent>
        <TabsContent value="rerank" className="mt-4">
          <RerankTab />
        </TabsContent>
        <TabsContent value="ner" className="mt-4">
          <NerTab />
        </TabsContent>
        <TabsContent value="raptor" className="mt-4">
          <RaptorTab />
        </TabsContent>
        <TabsContent value="inspector" className="mt-4">
          <InspectorTab />
        </TabsContent>
        <TabsContent value="performance" className="mt-4">
          <PerformanceTab />
        </TabsContent>
        <TabsContent value="cache" className="mt-4">
          <CacheTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ============================================================================
// Sağlık (Health) — taşındı: ./_tabs/health.tsx (PR-7b-6)
// ============================================================================

// ============================================================================
// Karşılaştırma (Benchmark) — taşındı: ./_tabs/benchmark.tsx (PR-7b-9)
// ============================================================================

// ============================================================================
// Atıf (Citation) — taşındı: ./_tabs/citation.tsx (PR-7b-2)
// ============================================================================

// ============================================================================
// Yeniden Sıralama (Reranker) — taşındı: ./_tabs/rerank.tsx (PR-7b-3)
// ============================================================================

// ============================================================================
// NER (#696 B5) — taşındı: ./_tabs/ner.tsx (PR-7b-5)
// ============================================================================

// ============================================================================
// RAPTOR — taşındı: ./_tabs/raptor.tsx (PR-7b-8)
// ============================================================================

// ============================================================================
// İnceleyici (Inspector) — taşındı: ./_tabs/inspector.tsx (PR-7b-10)
// ============================================================================

// ============================================================================
// Performans (Pipeline Comparison) — taşındı: ./_tabs/performance.tsx (PR-7b-7)
// ============================================================================

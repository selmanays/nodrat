"use client";

/**
 * /app/artifacts/[id] — Artefakt Canvas route sarmalayıcısı.
 *
 * Gövde `ArtifactCanvas` bileşenine taşındı (Faz A) → research thread içine
 * inline gömülebilir (Faz B). Bu route deep-link / küme detayından açma için
 * korunur (tam sayfa kabuğu, embedded=false).
 */

import { useParams } from "next/navigation";

import { ArtifactCanvas } from "@/components/research/ArtifactCanvas";

export default function ArtifactCanvasPage() {
  const params = useParams<{ id: string }>();
  return <ArtifactCanvas artifactId={params.id} />;
}

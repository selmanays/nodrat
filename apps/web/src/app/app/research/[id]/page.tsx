"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

/**
 * /app/research/[id] — eski route → birleşik /app/research?c={id} redirect (Faz C).
 *
 * Tek-route birleştirme sonrası thread artık /app/research?c={id}'de yaşar
 * (route-segment yok → giriş→stream sıçraması yok). Bu route yalnız eski
 * bookmark/link backward-compat için redirect eder.
 */
export default function ResearchThreadRedirect() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  useEffect(() => {
    if (params?.id) router.replace(`/app/research?c=${params.id}`);
  }, [params?.id, router]);
  return null;
}

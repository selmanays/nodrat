import Link from "next/link";
import { Layers } from "lucide-react";

import { Alert, AlertTitle } from "@/components/ui/alert";

/** Research cevabının altında "Bu içerik X kümesine eklendi" bağlam şeridi.
 * Backend stream-end 'artifact' SSE event'inden gelir (Faz 4 Dilim 2).
 *
 * Faz B: altına inline <ArtifactCanvas embedded> mount edildiğinden 'İçerik
 * kartını aç' CTA'sı kaldırıldı (kart zaten açık). shadcn <Alert> primitive
 * (preset idiom; elle border/bg div yerine) — küme adı AlertTitle'ın [&_a]
 * stilini alır, link küme detayına gider. */
export interface ResearchClusterLink {
  artifact_id: string;
  cluster_id: string;
  cluster_name: string;
}

/** #1762 — çoklu-küme: cevap birden çok kümeye ait olabilir. Birincil (baskın özne)
 * şeritte; ikincil kümeler (cevapta adı geçen diğer entity'ler) altta "Ayrıca ilgili"
 * chip'leri — kullanıcı o kümelere de geçebilir (keşif). */
export function ClusterLinkCard({
  link,
  secondaryClusters = null,
}: {
  link: ResearchClusterLink;
  secondaryClusters?: Array<{ cluster_id: string; cluster_name: string }> | null;
}) {
  return (
    <Alert>
      <Layers />
      <AlertTitle className="font-normal">
        Bu içerik{" "}
        <Link
          href={`/app/clusters/${link.cluster_id}?name=${encodeURIComponent(link.cluster_name)}`}
          className="font-medium"
        >
          {link.cluster_name}
        </Link>{" "}
        kümene eklendi.
        {secondaryClusters && secondaryClusters.length > 0 && (
          <span className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            Ayrıca ilgili:
            {secondaryClusters.map((c) => (
              <Link
                key={c.cluster_id}
                href={`/app/clusters/${c.cluster_id}?name=${encodeURIComponent(c.cluster_name)}`}
                className="rounded-full bg-muted px-2 py-0.5 font-medium text-foreground hover:bg-accent"
              >
                {c.cluster_name}
              </Link>
            ))}
          </span>
        )}
      </AlertTitle>
    </Alert>
  );
}

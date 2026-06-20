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

export function ClusterLinkCard({ link }: { link: ResearchClusterLink }) {
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
      </AlertTitle>
    </Alert>
  );
}

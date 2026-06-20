import Link from "next/link";
import { ArrowRight, FileText, Layers } from "lucide-react";

/** Research cevabının altında "Bu içerik X kümesine eklendi · kartı aç" bağı.
 * Backend stream-end 'artifact' SSE event'inden gelir (Faz 4 Dilim 2). */
export interface ResearchClusterLink {
  artifact_id: string;
  cluster_id: string;
  cluster_name: string;
}

export function ClusterLinkCard({ link }: { link: ResearchClusterLink }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-primary/30 bg-primary/5 px-4 py-3 text-sm">
      <Layers className="size-4 shrink-0 text-primary" />
      <span className="min-w-0">
        Bu içerik{" "}
        <Link
          href={`/app/clusters/${link.cluster_id}?name=${encodeURIComponent(link.cluster_name)}`}
          className="font-medium text-primary underline underline-offset-2"
        >
          {link.cluster_name}
        </Link>{" "}
        kümene eklendi.
      </span>
      <Link
        href={`/app/artifacts/${link.artifact_id}`}
        className="ml-auto inline-flex shrink-0 items-center gap-1 font-medium text-primary hover:underline"
      >
        <FileText className="size-4" />
        İçerik kartını aç
        <ArrowRight className="size-3.5" />
      </Link>
    </div>
  );
}

import { GenerationList } from "@/components/app/generation-list";

export default function SavedGenerationsPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Kayıtlı üretimler</h1>
        <p className="text-sm text-muted-foreground">
          Favorilerine eklediğin üretimler.
        </p>
      </div>
      <GenerationList savedOnly emptyTitle="Henüz kayıtlı üretim yok" />
    </div>
  );
}

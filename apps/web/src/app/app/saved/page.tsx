import { GenerationList } from "@/components/app/generation-list";

export default function SavedGenerationsPage() {
  return (
    <div className="space-y-6 max-w-4xl">
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

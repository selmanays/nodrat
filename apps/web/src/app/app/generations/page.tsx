import { GenerationList } from "@/components/app/generation-list";

export default function GenerationsHistoryPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Geçmiş üretimler</h1>
        <p className="text-sm text-muted-foreground">
          Tüm üretim isteklerin burada listelenir.
        </p>
      </div>
      <GenerationList />
    </div>
  );
}

/**
 * Landing page — Faz 0 placeholder.
 *
 * Kapsamlı landing tasarımı Faz 1+ ile gelecek.
 * docs/design/ux-wireframes.md §6 (TOFU)
 */

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <div className="max-w-2xl text-center space-y-6">
        <div className="inline-block rounded-full bg-accent-100 px-3 py-1 text-xs font-medium text-accent-900">
          Faz 0 — Hazırlık
        </div>

        <h1 className="text-4xl font-semibold tracking-tight text-brand-900 dark:text-foreground sm:text-5xl">
          Nodrat
        </h1>

        <p className="text-lg text-muted-foreground">
          Gündemi kaynaklı X içeriklerine dönüştüren{" "}
          <span className="font-medium text-foreground">
            editör odaklı üretim aracı
          </span>
          .
        </p>

        <p className="text-sm text-muted-foreground">
          MVP-1 hazırlık fazındayız.{" "}
          <a
            href="https://github.com/selmanays/nodrat"
            className="underline underline-offset-4 hover:text-foreground"
          >
            GitHub'da takip et
          </a>
          .
        </p>
      </div>
    </main>
  );
}

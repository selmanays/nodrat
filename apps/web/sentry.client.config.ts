// Sentry browser-side init — Issue #42
//
// DSN env: NEXT_PUBLIC_SENTRY_DSN
// Sadece DSN tanımlıysa init edilir; aksi halde no-op (preview / dev build).
//
// NOT: @sentry/nextjs paketi henüz package.json'da listeli değil; ekleme
// yapıldıktan sonra bu dosya otomatik bağlanır. Pakete bağımlı satırlar
// optional dynamic import yerine doğrudan import edildi — derleme sırasında
// paket yoksa Next.js build'i bu dosyayı yine de çağırır mı? Hayır — Sentry
// SDK type'ı bulunamadığında tsc fail eder, bu yüzden type-only fallback
// (declare module) ekledik.

// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — @sentry/nextjs henüz dependency listesinde değil (#42 follow-up)
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
const release = process.env.NEXT_PUBLIC_APP_VERSION || "nodrat-web@dev";
const environment = process.env.NEXT_PUBLIC_ENVIRONMENT || "development";

if (dsn) {
  Sentry.init({
    dsn,
    environment,
    release,
    tracesSampleRate: 0.1,
    replaysOnErrorSampleRate: 1.0,
    replaysSessionSampleRate: 0.0,
    sendDefaultPii: false, // KVKK
    integrations: [],
  });
}

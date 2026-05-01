// Sentry edge runtime init — Issue #42
// Edge runtime middleware/route handlers (örn. /monitoring tunnel) için
// gerekli. Server config ile aynı semantiği taşır.

// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — @sentry/nextjs henüz dependency listesinde değil (#42 follow-up)
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN || process.env.SENTRY_DSN;
const release = process.env.NEXT_PUBLIC_APP_VERSION || "nodrat-web@dev";
const environment = process.env.NEXT_PUBLIC_ENVIRONMENT || "development";

if (dsn) {
  Sentry.init({
    dsn,
    environment,
    release,
    tracesSampleRate: 0.1,
  });
}

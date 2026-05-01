/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,

  // Docker multi-stage build için standalone output (Dockerfile bekliyor)
  output: "standalone",

  // API proxy — local dev'de FastAPI'ye yönlendir
  // NOT: Production'da nginx zaten /api/ → 8000 proxy yapıyor; bu rewrite
  // sadece local dev için. Build sırasında env yoksa default kullan.
  async rewrites() {
    const apiBase = (
      process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    ).replace(/\/$/, "");
    return [
      {
        source: "/api/:path*",
        destination: `${apiBase}/:path*`,
      },
    ];
  },

  // Security headers (production'da Caddy de override eder)
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
          // 🚫 PRE-LAUNCH: arama motorları indekslemesin
          // Production launch sonra kaldır
          {
            key: "X-Robots-Tag",
            value: "noindex, nofollow, noarchive, nosnippet",
          },
        ],
      },
    ];
  },

  // Type check ve lint build sırasında zorla
  typescript: {
    ignoreBuildErrors: false,
  },
  eslint: {
    ignoreDuringBuilds: false,
  },
};

module.exports = nextConfig;

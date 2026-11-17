import type { NextConfig } from "next";

/** Matches ``python app.py`` (port 5000). Docker: FLASK_DEV_URL=http://127.0.0.1:8002 */
const flaskDevUrl = process.env.FLASK_DEV_URL ?? "http://127.0.0.1:5000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async headers() {
    // Allow UIC marketing site (and peers) to iframe embed slices.
    // Full app routes keep browser defaults; only `/embed/*` opts into framing.
    return [
      {
        source: "/embed/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value:
              "frame-ancestors 'self' https://urbanindigenouscollective.org https://*.urbanindigenouscollective.org https://*.squarespace.com https://*.sqsp.net",
          },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${flaskDevUrl}/api/:path*`,
      },
      {
        source: "/health-check",
        destination: `${flaskDevUrl}/health-check`,
      },
    ];
  },
};

export default nextConfig;

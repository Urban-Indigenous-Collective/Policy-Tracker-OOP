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
    // Public widget routes: allow any parent (GoDaddy editor preview hosts,
    // marketing site, etc.). Full app routes keep default framing protection.
    return [
      {
        source: "/embed/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: "frame-ancestors *",
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

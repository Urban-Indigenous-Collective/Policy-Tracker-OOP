import type { NextConfig } from "next";

const flaskDevUrl = process.env.FLASK_DEV_URL ?? "http://127.0.0.1:8000";

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

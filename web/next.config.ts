import type { NextConfig } from "next";

// Where the FastAPI backend runs. The browser only ever talks to this Next.js origin: /api/* is
// proxied, so the HttpOnly session cookie stays same-origin (no CORS, no third-party cookies).
const API_URL = process.env.FORTE_API_URL ?? "http://localhost:8000";

// Phone demo on the same Wi-Fi: FORTE_DEV_ORIGINS=192.168.1.23 (hostnames only, comma-separated).
const devOrigins = (process.env.FORTE_DEV_ORIGINS ?? "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  allowedDevOrigins: devOrigins,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;

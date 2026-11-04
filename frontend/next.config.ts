import type { NextConfig } from "next";

// The app is a static export served by FastAPI from `out/`, so production uses
// same-origin relative `/api/v1/...` URLs. Next.js rewrites/redirects/headers are
// NOT supported with `output: "export"` (see next/dist/docs/.../static-exports.md);
// local development therefore points at the backend with
// `NEXT_PUBLIC_API_BASE=http://localhost:8000` (read in lib/api.ts) instead of a proxy.
const nextConfig: NextConfig = {
  output: "export",
  images: {
    unoptimized: true,
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

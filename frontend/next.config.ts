import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // NEXT_DIST_DIR lets a production build run beside a live dev server without overwriting its .next folder.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // Next 16 blocks the dev server's scripts for origins it does not know; without this, opening http://127.0.0.1:3000 (not localhost) leaves every page unresponsive.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  /* config options here */
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
};

export default nextConfig;

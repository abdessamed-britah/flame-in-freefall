import type { NextConfig } from "next";

// Every page is prerendered as static HTML. The one exception is the route handler
// app/api/ask/route.ts (Node runtime), which runs the live chatbot on Vercel.
const nextConfig: NextConfig = {
  trailingSlash: true,
  images: { unoptimized: true },
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

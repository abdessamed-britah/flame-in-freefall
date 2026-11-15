import type { NextConfig } from "next";

// Every page is prerendered as static HTML. The one exception is the route handler
// app/api/ask/route.ts (Node runtime), which runs the live chatbot on Vercel.
const nextConfig: NextConfig = {
  trailingSlash: true,
  // the route reads this file at run time; make sure it is deployed with the function
  outputFileTracingIncludes: { "/api/ask": ["./data/rag_index.json"] },
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

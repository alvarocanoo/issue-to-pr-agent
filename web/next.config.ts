import type { NextConfig } from "next";

const isStatic = process.env.NEXT_PUBLIC_USE_STATIC === "true";
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig: NextConfig = {
  // Static export so GitHub Pages can host the dashboard without a Node runtime.
  ...(isStatic
    ? {
        output: "export",
        images: { unoptimized: true },
        basePath: basePath || undefined,
        assetPrefix: basePath || undefined,
        trailingSlash: true,
      }
    : {}),
};

export default nextConfig;

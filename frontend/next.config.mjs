import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  images: {
    formats: ["image/avif", "image/webp"],
    remotePatterns: [],
    // Only statically imported images may be optimized. Without this list
    // every local path qualifies, including /api/v1/* that the rewrite below
    // sends to the backend. Add a pattern here before optimizing files from
    // public/ (room images are authenticated blobs rendered `unoptimized`).
    localPatterns: [{ pathname: "/_next/static/media/**", search: "" }],
  },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${BACKEND_URL}/api/v1/:path*`,
      },
    ];
  },
};

export default withNextIntl(nextConfig);

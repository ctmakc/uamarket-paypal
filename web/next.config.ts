import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  poweredByHeader: false,
  images: { unoptimized: true },
  turbopack: { root: __dirname },
  agentRules: false,
  experimental: {
    // Next checks that an RSC request's `_rsc` value is the hash of its router headers and
    // answers a mismatch with a 307 to the "right" value. Behind the locale rewrite in
    // proxy.ts that check sent prefetches for English URLs back to themselves. The check
    // exists to stop a URL-keyed CDN cache from serving RSC payloads as HTML; every page
    // here is rendered per request with Cache-Control: no-store and nothing in front of
    // the storefront caches, so there is nothing for it to protect.
    validateRSCRequestHeaders: false,
  },
  async headers() {
    return [
      {
        source: "/admin/:path*",
        headers: [
          { key: "X-Robots-Tag", value: "noindex, nofollow" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
      {
        source: "/admin",
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }, { key: "X-Frame-Options", value: "DENY" }],
      },
      {
        source: "/fonts/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
      },
    ];
  },
};

export default nextConfig;

import { API_URL } from "@/lib/api";

/** Product photos live on the API's media volume; the shop serves them at the same /media path. */
export async function GET(_req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  if (path.some((p) => p === ".." || p.includes("/")) || !path.at(-1)?.endsWith(".webp")) {
    return new Response("Not found", { status: 404 });
  }
  const upstream = await fetch(`${API_URL}/media/${path.map(encodeURIComponent).join("/")}`, { cache: "no-store" }).catch(() => null);
  if (!upstream || !upstream.ok) return new Response("Not found", { status: upstream?.status === 404 ? 404 : 502 });
  return new Response(upstream.body, {
    status: 200,
    headers: {
      "content-type": "image/webp",
      "cache-control": upstream.headers.get("cache-control") || "public, max-age=31536000, immutable",
      "x-content-type-options": "nosniff",
    },
  });
}

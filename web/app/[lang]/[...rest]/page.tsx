import { notFound } from "next/navigation";

/**
 * Anything under a language that matches no route.
 *
 * web/proxy.ts rewrites every unprefixed address to /en/<path>, so a mistyped
 * or stale link used to land on /en/<anything>, match no child route and fall
 * out of the localised tree onto Next's built-in 404 — a bare page with no lang
 * attribute (WCAG 3.1.1), no header, no footer and no way back. This catch-all
 * is the last segment that still sits inside app/[lang]/layout.tsx, so calling
 * notFound() here reaches the written 404 with the shop's chrome around it.
 */
export const dynamic = "force-dynamic";

export default async function CatchAll() {
  notFound();
}

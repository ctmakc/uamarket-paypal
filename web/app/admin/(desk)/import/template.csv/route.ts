import { currentSession } from "@/lib/admin/session";
import { TEMPLATE_CSV } from "@/lib/admin/template";

/** The import template, for a signed-in owner. Source of truth: docs/catalogue-import-template.csv. */
export async function GET() {
  if (!(await currentSession())) return new Response("Sign in", { status: 401 });
  return new Response(TEMPLATE_CSV, {
    headers: { "content-type": "text/csv; charset=utf-8", "content-disposition": 'attachment; filename="catalogue-import-template.csv"', "cache-control": "no-store" },
  });
}

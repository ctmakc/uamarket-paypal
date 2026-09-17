import { cookies } from "next/headers";
import { ADMIN_LANG_COOKIE, type AdminLang } from "@/lib/admin/i18n";

export async function adminLang(): Promise<AdminLang> {
  const jar = await cookies();
  return jar.get(ADMIN_LANG_COOKIE)?.value === "uk" ? "uk" : "en";
}

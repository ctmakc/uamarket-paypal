"use client";

import { useEffect, useState } from "react";

/**
 * The SKU row of the specification table: the SKU of the variant chosen in the buy panel,
 * or every SKU of a one-variant piece. It follows the panel through a window event, so the
 * table can stay a server component.
 */
export default function SelectedSku({ initial }: { initial: string | null }) {
  const [sku, setSku] = useState<string | null>(initial);
  useEffect(() => {
    const on = (e: Event) => setSku((e as CustomEvent<{ sku: string | null }>).detail?.sku ?? null);
    window.addEventListener("uamarket:variant", on);
    return () => window.removeEventListener("uamarket:variant", on);
  }, []);
  return <span className="mono" data-spec-sku>{sku ?? "—"}</span>;
}

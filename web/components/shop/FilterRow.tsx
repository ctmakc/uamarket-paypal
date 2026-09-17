/**
 * One row of the filter chart: a mono label in the left column and the
 * controls beside it, wrapping under the label on a narrow screen.
 *
 * No new CSS class: the row is the same dashed count-major rule the rest of
 * the page uses between chart bands, and the controls sit in the existing
 * `.swatches` flow. The label column is 0.8 of a block wide on desktop, which
 * lines the rows up on the chart, and collapses to its own line below 720px
 * because the whole row is a wrapping flex line.
 */
import type { ReactNode } from "react";

export default function FilterRow({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: "var(--st)",
        paddingBlock: "var(--st)",
        borderBottom: "1px dashed var(--count-major)",
      }}
    >
      <span id={id} className="mono mono--sm muted" style={{ minWidth: "calc(var(--blk) * 0.8)" }}>
        {label}
      </span>
      <div className="swatches" role="group" aria-labelledby={id}>
        {children}
      </div>
    </div>
  );
}

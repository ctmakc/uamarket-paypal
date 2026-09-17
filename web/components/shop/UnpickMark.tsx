/**
 * The unpick mark: a cross-stitch drawn in a broken line, the way a stitch
 * looks while it is being taken out. It sits on a chip that removes a filter.
 *
 * Drawn, not an icon set and not a glyph from a font, and it inherits the
 * chip's own colour so it reads on linen and on the ink chip alike.
 */
export default function UnpickMark() {
  return (
    <svg className="mark" viewBox="0 0 14 14" aria-hidden="true" focusable="false">
      <path
        d="M3 3 L11 11 M11 3 L3 11"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="square"
        strokeDasharray="2 2"
        fill="none"
      />
    </svg>
  );
}

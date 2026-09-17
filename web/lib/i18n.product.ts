/**
 * Strings for the product page's depth blocks: the size guide, the provenance
 * expansion, the specification rows and the variant picker's honesty messages.
 *
 * `web/lib/i18n.ts` belongs to the orchestrator, so everything new that a buyer
 * reads on a product page lives here, in English and Ukrainian. Nothing in this
 * file states a measurement, a delivery time or a policy: the numbers all come
 * from the catalogue, and a sentence that would need a number the catalogue
 * does not carry says so instead.
 *
 * ---------------------------------------------------------------------------
 * THE ATTRIBUTE CONTRACT the size guide reads
 * ---------------------------------------------------------------------------
 * `Product.attributes` is a flat `Record<string, string | number>`, so the size
 * chart is stored as one key per cell. Nothing here is required; every key is
 * optional and the guide degrades to what it can prove.
 *
 *   size_<SIZE>_<measure>        one cell, e.g. `size_M_chest: 100`, `size_10_length: 62`
 *                                <SIZE>    the size token exactly as it appears in
 *                                          `variant.options.size` ("XS", "M", "XXL", "4", "12")
 *                                <measure> one of MEASURE_ORDER below; an unknown
 *                                          measure still renders, with its key humanised
 *   size_chart_unit              "cm" (assumed when absent) or "in"
 *   size_chart_note              one line on how the workshop measured, e.g. "garment
 *   size_chart_note_uk            measured flat, seam to seam". Shown verbatim.
 *
 * Cut facts, free text from the workshop, shown verbatim when present:
 *   fit, sleeve, closure, neckline, lining, cut  (+ a `_uk` twin for each)
 *
 * Piece dimensions, for things that have no size axis:
 *   length_cm, width_cm, height_cm, depth_cm, diameter_cm, volume_ml, weight_g
 *
 * A key that matches none of these still reaches the buyer: the specification
 * block prints every remaining attribute with its key humanised, so nothing a
 * workshop sends is silently dropped.
 */
import type { Lang } from "@/lib/i18n";

export type Origin = "HANDMADE_UA" | "MADE_UA" | "DESIGNED_UA";

export type ProductStrings = {
  details: string;
  description: string;
  spec: string;
  sizeGuide: {
    heading: string;
    link: string;
    sizeColumn: string;
    measuredIn: (unit: string) => string;
    offered: string;
    soldOut: string;
    fitHeading: string;
    missing: string;
    askLead: string;
    askNoEmail: string;
    mailSubject: (title: string) => string;
    faqLink: string;
  };
  provenance: {
    heading: string;
    link: string;
    lead: Record<Origin, string>;
    workshop: string;
    craft: string;
    since: string;
    technique: string;
    note: string;
    faqLink: string;
  };
  picker: {
    sizeNotInColour: (size: string, colour: string) => string;
    sizeComesIn: (colours: string) => string;
    sizeNowhere: (size: string) => string;
    soldOutIn: (colour: string) => string;
    colourAllSoldOut: string;
    unavailableHere: string;
    qtyMore: string;
    qtyLess: string;
    buyBar: string;
    chosen: string;
  };
  related: { inCollection: (name: string) => string };
  /** Column heads for the size chart, and labels for cut facts and dimensions. */
  measure: Record<string, string>;
  attribute: Record<string, string>;
  unit: { cm: string; in: string; ml: string; g: string };
};

const en: ProductStrings = {
  details: "Details",
  description: "About this piece",
  spec: "Specification",
  sizeGuide: {
    heading: "Size guide",
    link: "Size guide",
    sizeColumn: "Size",
    measuredIn: (unit) => `Measurements in ${unit}`,
    offered: "Sizes offered",
    soldOut: "sold out",
    fitHeading: "Cut and fit",
    missing: "Measurements per size are absent from the catalogue for this piece.",
    // What the shop can actually do: read the message and reply. The earlier
    // wording promised a workshop's answer inside a response time nothing in
    // the software measures.
    askLead: "Write to us with your own measurements and the size you are weighing up, and we answer.",
    askNoEmail: "The shop has published no contact address yet, so a size question has nowhere to go.",
    mailSubject: (title) => `Size question: ${title}`,
    faqLink: "How sizing questions are answered",
  },
  provenance: {
    heading: "What the mark means here",
    link: "What this mark means",
    lead: {
      HANDMADE_UA: "The red cross means a person made this piece by hand, in a Ukrainian workshop we name.",
      MADE_UA: "The running stitch means the piece was sewn or produced in Ukraine, with machine embroidery.",
      DESIGNED_UA: "The dotted square means Ukrainian design, produced outside Ukraine. We say so on the tag.",
    },
    workshop: "Workshop",
    craft: "Craft",
    since: "Working since",
    technique: "Technique",
    note: "From the workshop",
    faqLink: "How we use the three marks",
  },
  picker: {
    sizeNotInColour: (size, colour) => `Size ${size} is not offered in ${colour}.`,
    sizeComesIn: (colours) => `It comes in ${colours}.`,
    sizeNowhere: (size) => `Size ${size} is not offered for this piece.`,
    soldOutIn: (colour) => `Sold out in ${colour}.`,
    colourAllSoldOut: "every size sold out",
    unavailableHere: "Not offered",
    qtyMore: "Increase quantity",
    qtyLess: "Decrease quantity",
    buyBar: "Price and add to bag",
    chosen: "Chosen",
  },
  related: { inCollection: (name) => `More in ${name}` },
  measure: {
    chest: "Chest",
    waist: "Waist",
    hips: "Hips",
    shoulder: "Shoulders",
    sleeve: "Sleeve length",
    length: "Length",
    back_length: "Back length",
    inseam: "Inseam",
    neck: "Neck",
    hem: "Hem width",
    rise: "Rise",
  },
  attribute: {
    fit: "Fit",
    sleeve: "Sleeve",
    closure: "Closure",
    neckline: "Neckline",
    lining: "Lining",
    cut: "Cut",
    length_cm: "Length",
    width_cm: "Width",
    height_cm: "Height",
    depth_cm: "Depth",
    diameter_cm: "Diameter",
    volume_ml: "Volume",
    weight_g: "Weight",
  },
  unit: { cm: "cm", in: "in", ml: "ml", g: "g" },
};

const uk: ProductStrings = {
  details: "Деталі",
  description: "Про цю річ",
  spec: "Характеристики",
  sizeGuide: {
    heading: "Розмірна сітка",
    link: "Розмірна сітка",
    sizeColumn: "Розмір",
    measuredIn: (unit) => `Мірки в ${unit}`,
    offered: "Пропоновані розміри",
    soldOut: "розпродано",
    fitHeading: "Крій і посадка",
    missing: "Мірок за розмірами для цієї речі в каталозі немає.",
    askLead: "Напишіть нам свої мірки та розмір, який обираєте, і ми відповімо.",
    askNoEmail: "Крамниця ще не опублікувала контактної адреси, тож питання про розмір нікуди надіслати.",
    mailSubject: (title) => `Питання про розмір: ${title}`,
    faqLink: "Як ми відповідаємо на питання про розмір",
  },
  provenance: {
    heading: "Що означає цей знак тут",
    link: "Що означає цей знак",
    lead: {
      HANDMADE_UA: "Червоний хрестик означає, що цю річ зробила руками людина в українській майстерні, яку ми називаємо.",
      MADE_UA: "Стібок уперед голку означає, що річ пошито або виготовлено в Україні, з машинною вишивкою.",
      DESIGNED_UA: "Пунктирний квадрат означає український дизайн і виготовлення за межами України. Ми пишемо про це на бирці.",
    },
    workshop: "Майстерня",
    craft: "Ремесло",
    since: "Працює з",
    technique: "Техніка",
    note: "Від майстерні",
    faqLink: "Як ми користуємось трьома знаками",
  },
  picker: {
    sizeNotInColour: (size, colour) => `Розміру ${size} немає в кольорі «${colour}».`,
    sizeComesIn: (colours) => `Він є в кольорах: ${colours}.`,
    sizeNowhere: (size) => `Розміру ${size} для цієї речі немає.`,
    soldOutIn: (colour) => `Розпродано в кольорі «${colour}».`,
    colourAllSoldOut: "усі розміри розпродані",
    unavailableHere: "Немає",
    qtyMore: "Збільшити кількість",
    qtyLess: "Зменшити кількість",
    buyBar: "Ціна та додавання до кошика",
    chosen: "Обрано",
  },
  related: { inCollection: (name) => `Більше в колекції «${name}»` },
  measure: {
    chest: "Обхват грудей",
    waist: "Обхват талії",
    hips: "Обхват стегон",
    shoulder: "Ширина плечей",
    sleeve: "Довжина рукава",
    length: "Довжина виробу",
    back_length: "Довжина по спинці",
    inseam: "Довжина по внутрішньому шву",
    neck: "Обхват шиї",
    hem: "Ширина по низу",
    rise: "Висота посадки",
  },
  attribute: {
    fit: "Посадка",
    sleeve: "Рукав",
    closure: "Застібка",
    neckline: "Виріз",
    lining: "Підкладка",
    cut: "Крій",
    length_cm: "Довжина",
    width_cm: "Ширина",
    height_cm: "Висота",
    depth_cm: "Глибина",
    diameter_cm: "Діаметр",
    volume_ml: "Об'єм",
    weight_g: "Вага",
  },
  unit: { cm: "см", in: "дюйми", ml: "мл", g: "г" },
};

/** The product page's own dictionary. */
export function tpd(lang: Lang): ProductStrings {
  return lang === "uk" ? uk : en;
}

/** Column order of a size chart; measures outside this list follow, as given. */
export const MEASURE_ORDER = [
  "chest",
  "waist",
  "hips",
  "shoulder",
  "sleeve",
  "length",
  "back_length",
  "inseam",
  "neck",
  "hem",
  "rise",
] as const;

/** Free-text cut facts, in the order a buyer reads them. */
export const FIT_KEYS = ["fit", "cut", "sleeve", "neckline", "closure", "lining"] as const;

/** Whole-piece dimensions, for things sold without a size. */
export const DIMENSION_KEYS = [
  "length_cm",
  "width_cm",
  "height_cm",
  "depth_cm",
  "diameter_cm",
  "volume_ml",
  "weight_g",
] as const;

/** The unit a dimension key carries in its own name. */
export function dimensionUnit(key: string, lang: Lang): string {
  const u = tpd(lang).unit;
  if (key.endsWith("_cm")) return u.cm;
  if (key.endsWith("_ml")) return u.ml;
  if (key.endsWith("_g")) return u.g;
  return "";
}

/** A key we have no translation for still reaches the buyer, readably. */
export function humanise(key: string): string {
  const words = key.replace(/_/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Label for an attribute key: translated when we know it, humanised when not. */
export function attributeLabel(lang: Lang, key: string): string {
  return tpd(lang).attribute[key] ?? humanise(key);
}

/** Label for a size-chart column: translated when we know it, humanised when not. */
export function measureLabel(lang: Lang, key: string): string {
  return tpd(lang).measure[key] ?? humanise(key);
}

/** "a, b and c" / "a, b та c" — the shop's list voice, in both locales. */
export function listWords(lang: Lang, words: string[]): string {
  if (words.length <= 1) return words[0] ?? "";
  const last = words[words.length - 1];
  return `${words.slice(0, -1).join(", ")} ${lang === "uk" ? "та" : "and"} ${last}`;
}

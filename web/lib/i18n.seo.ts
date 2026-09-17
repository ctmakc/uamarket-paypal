/**
 * Strings owned by the SEO layer.
 *
 * `web/lib/i18n.ts` belongs to the orchestrator, so every string this layer
 * needs lives here, in English and Ukrainian. Facts used in the copy come from
 * the storefront config and DESIGN.md: the shop ships inside Canada.
 */
import type { Lang } from "@/lib/i18n";

export type SeoDict = {
  /** Small line above the title on the social card. */
  ogKicker: string;
  /** Alt text for the generated social card. */
  ogAlt: (title: string) => string;
  /** Title drawn on the card when the caller passes none. */
  ogTitleFallback: string;
  /** Accessible label of the cross-stitch chart drawn on the card. */
  ogChartLabel: string;
};

const seo: Record<Lang, SeoDict> = {
  en: {
    ogKicker: "Ukrainian goods · Canada",
    ogAlt: (title: string) => `${title} — UA Market, a counted cross-stitch chart on linen`,
    ogTitleFallback: "Ukrainian things, counted stitch by stitch",
    ogChartLabel: "Cross-stitch chart",
  },
  uk: {
    ogKicker: "Українські речі · Канада",
    ogAlt: (title: string) => `${title} — UA Market, лічена схема хрестиком на полотні`,
    ogTitleFallback: "Українські речі, лічені стібок за стібком",
    ogChartLabel: "Схема для вишивки хрестиком",
  },
};

/**
 * A proposed search title and description for the front page and the shop, written around
 * the words people search with (vyshyvanka, rushnyk, motanka, Opishnia). Off by default:
 * SEO_USE_PROPOSED_TITLES=true switches them on once the owner has approved the wording
 * (docs/OWNER-ACTIONS.md). Until then the pages keep the shop's own hero line.
 */
export const PROPOSED_SEO: Record<Lang, { homeTitle: string; homeDescription: string; shopTitle: string }> = {
  en: {
    homeTitle: "Ukrainian vyshyvanky, rushnyky and gifts, shipped in Canada · UA Market",
    homeDescription: "Embroidered vyshyvanka shirts and blouses, rushnyky, motanka dolls and Opishnia ceramics from named Ukrainian makers, shipped across Canada.",
    shopTitle: "Shop vyshyvanky, rushnyky and Ukrainian gifts",
  },
  uk: {
    homeTitle: "Вишиванки, рушники й українські подарунки з доставкою по Канаді · UA Market",
    homeDescription: "Вишиванки, рушники, ляльки-мотанки та опішнянська кераміка від названих українських майстрів із доставкою по Канаді.",
    shopTitle: "Вишиванки, рушники й українські подарунки",
  },
};

export function proposedSeoOn(): boolean {
  return (process.env.SEO_USE_PROPOSED_TITLES || "").trim().toLowerCase() === "true";
}

export function seoText(lang: Lang): SeoDict {
  return seo[lang] ?? seo.en;
}

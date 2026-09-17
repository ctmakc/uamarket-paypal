/**
 * Everything the storefront says about locker pickup, in one place, in both languages.
 *
 * Why a module of its own. Until now three separate files each carried their own
 * sentence about the bay code, and every one of them promised something the software
 * could not do: the FAQ said "you receive a one-time code for a locker bay, and the
 * address travels with the code", the shipping page said the same, and the order page
 * said the code is not on it. The fulfillment core minted the code for the operator who
 * packed the parcel and for nobody else, so the shop was selling a delivery method it
 * had no way of delivering.
 *
 * The core now has a customer side (docs/OWNER-ACTIONS.md, section 8), and every
 * sentence below is a function of what that side actually does on THIS deployment:
 *
 *   - the address, the hours and the door note are printed only when the owner has
 *     configured them, exactly as they were typed. There is no default address and
 *     there never will be one — the street a buyer walks to is a fact about a building
 *     in Ottawa, and this repository does not know it;
 *   - `enabled` is the only key a page branches on. The API sets it true only when the
 *     switch is on AND an address exists, so a shop that has not said where the locker
 *     is stops offering pickup, and these sentences fall back to saying so and pointing
 *     at the courier;
 *   - how the code reaches the buyer depends on whether the shop can send email at all.
 *     With SMTP unconfigured the order page is the only channel, and the copy says that
 *     rather than promising a message the server will not send;
 *   - how long the code lives is `PICKUP_CODE_VALID_HOURS`, printed as the number it
 *     is set to.
 *
 * Nothing here invents a fact, and nothing here implies a code that has not been minted.
 */
import type { PickupConfig } from "@/lib/api";
import type { Lang } from "@/lib/i18n";
import { pick, plural } from "@/lib/i18n";

/** The shape both this module and lib/content.ts use for a two-language string. */
export type Bilingual = { en: string; uk: string };

function hours(n: number): Bilingual {
  return { en: `${n} ${n === 1 ? "hour" : "hours"}`, uk: `${n} ${plural(n, "годину", "години", "годин")}` };
}

/* ------------------------------------------------------------------ the order page */

const orderCopy = {
  en: {
    /** Above the digits. */
    code: "Your one-time code",
    bay: (id: string) => `Bay ${id}`,
    address: "Address",
    hours: "Hours",
    door: "At the door",
    until: (when: string) => `The code works until ${when}.`,
    lasts: (n: number) => `A code lasts ${hours(n).en} from the moment the parcel goes in.`,
    /** Read aloud to a screen reader, digit by digit, so 006 is not heard as "six". */
    codeSpoken: (digits: string) => `Your one-time code: ${digits.split("").join(" ")}`,
  },
  uk: {
    code: "Ваш одноразовий код",
    bay: (id: string) => `Комірка ${id}`,
    address: "Адреса",
    hours: "Години",
    door: "Біля дверей",
    until: (when: string) => `Код працює до ${when}.`,
    lasts: (n: number) => `Код діє ${hours(n).uk} від моменту, коли посилка потрапляє в комірку.`,
    codeSpoken: (digits: string) => `Ваш одноразовий код: ${digits.split("").join(" ")}`,
  },
};

export type PickupOrderCopy = typeof orderCopy.en;

export function tpk(lang: Lang): PickupOrderCopy {
  return lang === "uk" ? (orderCopy.uk as PickupOrderCopy) : orderCopy.en;
}

/* -------------------------------------------------------------------- the checkout */

/**
 * The pickup option as the checkout prints it: the name the owner gave the method, and
 * under it the two facts that decide whether a person can use it — where they would be
 * walking to, and when. Both come from the live config, so on a deployment without an
 * address the option is absent altogether and this function is never called.
 */
export function pickupOption(cfg: PickupConfig, lang: Lang, free: string): { label: string; lines: string[] } {
  const lines: string[] = [];
  const where = cfg.address ? `${free} · ${cfg.address}` : free;
  lines.push(where);
  const second = lang === "uk"
    ? `${cfg.hours ? `${cfg.hours}. ` : ""}Одноразовий код відкриває комірку, коли посилка вже в локері.`
    : `${cfg.hours ? `${cfg.hours}. ` : ""}A one-time code opens the bay once the parcel is in the locker.`;
  lines.push(second);
  return { label: pick(lang, cfg.label, cfg.label_uk), lines };
}

/* ------------------------------------------------------ the FAQ and the policy page */

export type PickupCopyInput = {
  cfg: PickupConfig;
  /** Whether the shop can send email at all — /v1/storefront/config, `notifications`. */
  mail: boolean;
  /** Where a customer writes, when the shop has published an address. */
  contact: string | null;
  /** The courier fallback, printed when pickup is unavailable. */
  shipping: { flat: Bilingual; free: Bilingual } | null;
  /**
   * A Ukrainian rendering of the hours, from SHOP_PICKUP_HOURS_UK. The API knows one
   * string and cannot translate it, so a shop that wants Ukrainian opening hours sets
   * this second setting; unset, both languages print the one string the owner typed.
   */
  hoursUk?: string | null;
};

/** The hours in both languages: the API's string, with the Ukrainian override when set. */
function openHours(cfg: PickupConfig, hoursUk?: string | null): Bilingual | null {
  if (!cfg.hours) return null;
  return { en: cfg.hours, uk: (hoursUk || "").trim() || cfg.hours };
}

/**
 * What the pages say when the shop's settings could not be read at all. The pickup
 * sentences elsewhere describe a switch and an address; neither is knowable here, so the
 * page says which question it cannot answer.
 */
export const PICKUP_UNKNOWN: Bilingual = {
  en: "This page could not check whether locker pickup is open today. Checkout shows the delivery choices you can actually pick.",
  uk: "Ця сторінка не змогла перевірити, чи працює сьогодні самовивіз із локера. Сторінка оформлення показує ті способи доставки, які справді можна обрати.",
};

/** How the code reaches the buyer on this deployment. One sentence, both languages. */
function delivery(mail: boolean): Bilingual {
  return mail
    ? {
        en: "It is emailed to you, and your order page carries the same code.",
        uk: "Він надходить вам електронною поштою, і той самий код показує сторінка вашого замовлення.",
      }
    : {
        en: "Your order page carries it. The shop sends no email yet, so the person who packs the parcel is the one who passes the code on.",
        uk: "Його показує сторінка вашого замовлення. Крамниця поки не надсилає листів, тож код передає людина, яка пакує посилку.",
      };
}

/** Why pickup is missing from the checkout, and what happens to an order instead. */
export function pickupUnavailable({ cfg, shipping }: Pick<PickupCopyInput, "cfg" | "shipping">): Bilingual {
  const courier: Bilingual = shipping
    ? {
        en: ` Every order travels by courier: ${shipping.flat.en} flat within Canada, free once the bag reaches ${shipping.free.en}.`,
        uk: ` Кожне замовлення їде кур'єрською службою: ${shipping.flat.uk} по Канаді, безкоштовно від ${shipping.free.uk} у кошику.`,
      }
    : {
        en: " Every order travels by courier, and checkout prints the delivery amount before the order is placed.",
        uk: " Кожне замовлення їде кур'єрською службою, а суму доставки сторінка оформлення друкує до підтвердження замовлення.",
      };
  // Two different silences, and a customer deserves to know which one this is: a method
  // the owner switched off, or a method waiting on an address the owner has not sent.
  const head: Bilingual = cfg.switch_on
    ? {
        en: "Pickup is unavailable at the moment: the locker address is not published yet, so checkout does not offer it.",
        uk: "Самовивіз наразі недоступний: адресу локера ще не опубліковано, тож при оформленні його немає.",
      }
    : {
        en: "Locker pickup is closed at the moment.",
        uk: "Самовивіз із локера наразі не працює.",
      };
  return { en: head.en + courier.en, uk: head.uk + courier.uk };
}

/** The FAQ answer to "Can I pick the order up instead?". */
export function pickupAnswer(input: PickupCopyInput): Bilingual {
  const { cfg, mail, contact } = input;
  if (!cfg.enabled) return pickupUnavailable(input);
  const label = { en: cfg.label, uk: cfg.label_uk };
  const open = openHours(cfg, input.hoursUk);
  const where: Bilingual = {
    en: `The locker is at ${cfg.address}${open ? `, ${open.en}` : ""}.`,
    uk: `Локер стоїть за адресою ${cfg.address}${open ? `, ${open.uk}` : ""}.`,
  };
  const how = delivery(mail);
  const life = hours(cfg.code_valid_hours);
  const expiry: Bilingual = {
    en: ` The code works for ${life.en} and opens that one bay once; when the hours run out it stops working, and ${
      contact ? `a note to ${contact}` : "a note to the shop"
    } with the order number gets you a fresh one.`,
    uk: ` Код діє ${life.uk} і відкриває цю саму комірку один раз; коли години спливають, він перестає працювати, а щоб отримати новий, напишіть ${
      contact ? `на ${contact}` : "у крамницю"
    } й вкажіть номер замовлення.`,
  };
  return {
    en: `Yes: choose “${label.en}” at checkout and pay nothing for delivery. ${where.en} Your one-time code for a bay is issued the moment the packer puts the parcel in it. ${how.en}${expiry.en}`,
    uk: `Так: оберіть «${label.uk}» під час оформлення й нічого не платіть за доставку. ${where.uk} Одноразовий код до комірки видається тієї миті, коли пакувальник кладе в неї посилку. ${how.uk}${expiry.uk}`,
  };
}

/**
 * The "Locker pickup" section of the shipping page, in the order it is read: what the
 * method costs, where the locker is, when the code appears and how long it lives.
 * `facts` is a label/value set that the policy page prints as ruled rows.
 */
export type PickupPolicyCopy = {
  intro: Bilingual;
  facts: { label: Bilingual; value: Bilingual }[];
  code: Bilingual;
  expiry: Bilingual;
  labelled: Bilingual;
};

export function pickupPolicy({ cfg, mail, contact, hoursUk }: PickupCopyInput): PickupPolicyCopy {
  const life = hours(cfg.code_valid_hours);
  const how = delivery(mail);
  const open = openHours(cfg, hoursUk);
  const facts: { label: Bilingual; value: Bilingual }[] = [
    {
      label: { en: "Where the locker is", uk: "Де стоїть локер" },
      value: { en: cfg.address ?? "", uk: cfg.address ?? "" },
    },
  ];
  if (open) {
    facts.push({
      label: { en: "When it can be reached", uk: "Коли до нього можна дістатися" },
      value: open,
    });
  }
  if (cfg.note) {
    facts.push({
      label: { en: "At the door", uk: "Біля дверей" },
      value: { en: cfg.note, uk: cfg.note },
    });
  }
  return {
    intro: {
      en: `Pickup is chosen at checkout and costs nothing.${
        open ? "" : " The hours the locker can be reached are not published yet, so ask when your code arrives."
      }`,
      uk: `Самовивіз обирається під час оформлення й нічого не коштує.${
        open ? "" : " Години, коли до локера можна дістатися, ще не опубліковано, тож запитайте, коли прийде ваш код."
      }`,
    },
    facts,
    code: {
      en: `The one-time code for your bay is issued the moment the packer puts the parcel in it. ${how.en} It opens that one bay, once, and it works for ${life.en} from the moment the parcel goes in.`,
      uk: `Одноразовий код до вашої комірки видається тієї миті, коли пакувальник кладе в неї посилку. ${how.uk} Він відкриває цю саму комірку один раз і діє ${life.uk} від моменту, коли посилка туди потрапляє.`,
    },
    expiry: {
      en: `When the hours run out the code stops working and your order page says so. ${
        contact ? `Write to ${contact} with the order number` : "Write to the shop with the order number"
      } and a fresh code is issued for the same parcel.`,
      uk: `Коли години спливають, код перестає працювати, і сторінка вашого замовлення про це повідомляє. ${
        contact ? `Напишіть на ${contact} і вкажіть номер замовлення` : "Напишіть у крамницю й вкажіть номер замовлення"
      } — на ту саму посилку видадуть новий код.`,
    },
    labelled: {
      en: `The pickup option is labelled “${cfg.label}” at checkout, and your order page carries the address, the hours and the code from the moment the parcel is in the locker.`,
      uk: `На сторінці оформлення цей варіант підписано «${cfg.label_uk}», а сторінка вашого замовлення несе адресу, години та код від миті, коли посилка опиняється в локері.`,
    },
  };
}

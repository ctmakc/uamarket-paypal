/**
 * Strings added in wave 3 for buying on a phone and in Ukrainian: the bag header, the
 * add-to-bag toast, the gallery, the filter drawer, search suggestions, checkout acceptance
 * and field messages, the order steps, the seller block, and the "catching up" page.
 * Every entry exists in English and Ukrainian and states only what the code does.
 */
import type { Lang } from "@/lib/i18n";
import { plural } from "@/lib/i18n";

/** Variant labels the catalogue writes in English when no Ukrainian one was entered. */
const GENERIC_LABELS_UK: Record<string, string> = { "One size": "Один розмір" };

const strings = {
  en: {
    bagHeading: "Your bag",
    bagCount: (n: number) => `${n} ${n === 1 ? "item" : "items"}`,
    bagQuoteFailed: "Prices could not be checked just now. The bag is saved; try again in a minute.",
    toastAdded: (title: string) => `Added to your bag: ${title}`,
    toastView: "View bag",
    toastCheckout: "Checkout",
    toastClose: "Close",
    gallery: {
      region: "Photos",
      show: (n: number, of: number) => `Show photo ${n} of ${of}`,
      open: "Open the photo full screen",
      close: "Close full screen",
      prev: "Previous photo",
      next: "Next photo",
      counter: (n: number, of: number) => `${n} / ${of}`,
    },
    sku: "SKU",
    filters: {
      open: "Filter · Sort",
      openCount: (n: number) => `Filter · Sort (${n})`,
      title: "Filter and sort",
      done: (n: number) => `Show ${n} ${n === 1 ? "piece" : "pieces"}`,
      close: "Close",
    },
    searchOpen: "Search the shop",
    searchClose: "Close search",
    suggestCategory: (name: string) => `Nothing matched. The closest shelf: ${name}`,
    suggestLead: "Nothing matched these words.",
    suggestShelf: "The closest shelf",
    checkout: {
      accept: "I accept the",
      terms: "terms of sale",
      and: "and the",
      privacy: "privacy notice",
      acceptError: "Tick the box to accept the terms of sale and the privacy notice.",
      province: (reason: string) => reason,
      postal: "Enter a postal code like K1A 0B1.",
      street1: "Enter the street address.",
      city: "Enter the city.",
    },
    steps: {
      label: "Progress",
      ship: ["Placed", "Paid", "Packed", "Shipped"],
      pickup: ["Placed", "Paid", "Packed", "In the locker", "Collected"],
    },
    gst: (n: string) => `GST/HST registration: ${n}`,
    lookupBusy: "Too many lookups from this connection. Wait a few minutes and try again.",
    lookupDown: "The shop is catching up and could not look the order up. Try again in a minute.",
    seller: {
      heading: "Who sells",
      legalName: "Seller",
      address: "Business address",
      contact: "Contact",
      privacy: "Privacy questions",
      gst: "GST/HST number",
      unpublished: "not published yet",
      tradingName: (name: string) => `${name} (trading name; the registered name is not published yet)`,
    },
    processors: {
      heading: "Services that handle your data for the shop",
      email: "Order email",
      payments: "Card payments",
      shipping: "Shipping labels",
      hosting: "Hosting",
      unnamed: "not published yet",
    },
    confirmLine: (contact: string | null) =>
      contact ? `We'll confirm this before the shop opens. Questions: ${contact}` : "We'll confirm this before the shop opens.",
    excluded: (names: string) => `We do not ship to ${names} yet.`,
    down: {
      title: "The shop is catching up",
      body: "The catalogue could not be read just now. Try again in a minute. Your bag is saved in this browser.",
      retry: "Try again",
    },
  },
  uk: {
    bagHeading: "Кошик",
    bagCount: (n: number) => `${n} ${plural(n, "товар", "товари", "товарів")}`,
    bagQuoteFailed: "Ціни зараз перевірити не вдалося. Кошик збережено; спробуйте за хвилину.",
    toastAdded: (title: string) => `Додано до кошика: ${title}`,
    toastView: "До кошика",
    toastCheckout: "Оформити",
    toastClose: "Закрити",
    gallery: {
      region: "Фото",
      show: (n: number, of: number) => `Показати фото ${n} з ${of}`,
      open: "Відкрити фото на весь екран",
      close: "Закрити повноекранний перегляд",
      prev: "Попереднє фото",
      next: "Наступне фото",
      counter: (n: number, of: number) => `${n} / ${of}`,
    },
    sku: "Артикул",
    filters: {
      open: "Фільтр · Порядок",
      openCount: (n: number) => `Фільтр · Порядок (${n})`,
      title: "Фільтр і порядок",
      done: (n: number) => `Показати ${n} ${plural(n, "річ", "речі", "речей")}`,
      close: "Закрити",
    },
    searchOpen: "Пошук у крамниці",
    searchClose: "Закрити пошук",
    suggestCategory: (name: string) => `Нічого не знайшлося. Найближча полиця: ${name}`,
    suggestLead: "За цими словами нічого не знайшлося.",
    suggestShelf: "Найближча полиця",
    checkout: {
      accept: "Я приймаю",
      terms: "умови продажу",
      and: "та",
      privacy: "повідомлення про приватність",
      acceptError: "Поставте позначку, щоб прийняти умови продажу та повідомлення про приватність.",
      province: (reason: string) => reason,
      postal: "Введіть поштовий індекс на кшталт K1A 0B1.",
      street1: "Введіть вулицю й номер будинку.",
      city: "Введіть місто.",
    },
    steps: {
      label: "Хід замовлення",
      ship: ["Оформлено", "Оплачено", "Спаковано", "Відправлено"],
      pickup: ["Оформлено", "Оплачено", "Спаковано", "У локері", "Забрано"],
    },
    gst: (n: string) => `Реєстрація GST/HST: ${n}`,
    lookupBusy: "Забагато пошуків із цього з'єднання. Зачекайте кілька хвилин і спробуйте знову.",
    lookupDown: "Крамниця оновлюється й не змогла знайти замовлення. Спробуйте за хвилину.",
    seller: {
      heading: "Хто продає",
      legalName: "Продавець",
      address: "Адреса підприємства",
      contact: "Зв'язок",
      privacy: "Питання приватності",
      gst: "Номер GST/HST",
      unpublished: "ще не опубліковано",
      tradingName: (name: string) => `${name} (торгова назва; зареєстровану назву ще не опубліковано)`,
    },
    processors: {
      heading: "Сервіси, що обробляють ваші дані для крамниці",
      email: "Листи про замовлення",
      payments: "Оплата карткою",
      shipping: "Етикетки доставки",
      hosting: "Хостинг",
      unnamed: "ще не опубліковано",
    },
    confirmLine: (contact: string | null) =>
      contact ? `Ми підтвердимо це до відкриття крамниці. Питання: ${contact}` : "Ми підтвердимо це до відкриття крамниці.",
    excluded: (names: string) => `Поки що ми не доставляємо в ${names}.`,
    down: {
      title: "Крамниця оновлюється",
      body: "Каталог зараз не вдалося прочитати. Спробуйте за хвилину. Кошик збережено в цьому браузері.",
      retry: "Спробувати ще раз",
    },
  },
};

export type BuyStrings = typeof strings.en;

export function tb(lang: Lang): BuyStrings {
  return lang === "uk" ? (strings.uk as BuyStrings) : strings.en;
}

/** A variant label in the page's language: the Ukrainian one, or a known generic translated. */
export function variantLabel(lang: Lang, label: string | null | undefined, labelUk: string | null | undefined): string {
  if (lang === "uk") {
    if (labelUk) return labelUk;
    if (label && GENERIC_LABELS_UK[label]) return GENERIC_LABELS_UK[label];
  }
  return label || "";
}

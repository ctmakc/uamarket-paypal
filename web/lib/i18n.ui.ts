/**
 * Strings for the site chrome: skip link, mobile menu, skeletons, the error
 * boundary and the 404 page.
 *
 * web/lib/i18n.ts belongs to the orchestrator, so anything the polish pass
 * needed to say lives here instead. Every entry exists in English and in
 * Ukrainian; nothing here states a fact about the shop.
 */
import type { Lang } from "@/lib/i18n";
import { plural } from "@/lib/i18n";

const strings = {
  en: {
    skip: "Skip to the shop",
    menu: "Menu",
    menuClose: "Close",
    menuPanel: "Site menu",
    searchGo: "Search",
    bagCount: (n: number) => (n === 0 ? "Bag, empty" : `Bag, ${n} ${n === 1 ? "item" : "items"}`),
    loading: "Loading the page",
    soldOut: "Sold out",
    /** The bag's own controls: every one of them names the piece it acts on. */
    bag: {
      /** The receipt's last row. Shipping is settled at checkout, so this row
       *  is the goods on their own and says so. */
      goodsTotal: "Total for the goods",
      quantity: (title: string) => `Quantity: ${title}`,
      less: (title: string) => `One fewer: ${title}`,
      more: (title: string) => `One more: ${title}`,
      remove: (title: string) => `Remove: ${title}`,
      removed: (title: string, left: number) =>
        left === 0 ? `${title} taken out. The bag is empty.` : `${title} taken out. ${left} ${left === 1 ? "line" : "lines"} left.`,
      changes: "Bag changes",
    },
    placeholder:
      "Preview. This deployment carries a placeholder assortment used to build and test the shop. The products, prices and makers here are demonstration data, and the pictures are generated images of the kind of piece described.",
    pages: {
      heading: "Terms",
      faq: "Questions and answers",
      shipping: "Shipping and pickup",
      care: "Care",
      privacy: "Privacy",
      terms: "Terms of sale",
    },
    error: {
      title: "This page stopped while loading",
      body: "Something in the page failed. The bag stored in your browser is unchanged.",
      retry: "Load the page again",
      shop: "Go to the shop",
      ref: "Error reference",
    },
    notFound: {
      code: "404",
      title: "This page is not on the chart",
      body: "The address matches no page in the shop. It may have moved, or the link may carry a typo.",
      shop: "Shop everything",
      makers: "Meet the makers",
      home: "Front page",
      searchLead: "Or look for a piece by name.",
    },
    /** The order-lookup form, when the shop sends no email. */
    orderLookupNoEmail: "Enter the order number you kept after placing the order, and the email you used.",
  },
  uk: {
    skip: "Перейти до вмісту",
    menu: "Меню",
    menuClose: "Закрити",
    menuPanel: "Меню сайту",
    searchGo: "Знайти",
    bagCount: (n: number) => (n === 0 ? "Кошик, порожній" : `Кошик, ${n} ${plural(n, "товар", "товари", "товарів")}`),
    loading: "Сторінка завантажується",
    soldOut: "Розпродано",
    bag: {
      goodsTotal: "Разом за товари",
      quantity: (title: string) => `Кількість: ${title}`,
      less: (title: string) => `На одну менше: ${title}`,
      more: (title: string) => `На одну більше: ${title}`,
      remove: (title: string) => `Прибрати: ${title}`,
      removed: (title: string, left: number) =>
        left === 0
          ? `${title} прибрано. Кошик порожній.`
          : `${title} прибрано. Залишилося ${left} ${plural(left, "позиція", "позиції", "позицій")}.`,
      changes: "Зміни в кошику",
    },
    placeholder:
      "Попередній перегляд. Це розгортання містить тимчасовий асортимент для збирання й тестування крамниці. Товари, ціни та майстри тут — демонстраційні дані, а зображення згенеровані й показують тип описаної речі.",
    pages: {
      heading: "Умови",
      faq: "Питання та відповіді",
      shipping: "Доставка та самовивіз",
      care: "Догляд",
      privacy: "Приватність",
      terms: "Умови продажу",
    },
    error: {
      title: "Ця сторінка зупинилася під час завантаження",
      body: "Щось у сторінці не спрацювало. Кошик, збережений у вашому браузері, не змінився.",
      retry: "Завантажити сторінку ще раз",
      shop: "До крамниці",
      ref: "Код помилки",
    },
    notFound: {
      code: "404",
      title: "Цієї сторінки немає на схемі",
      body: "Адреса не збігається з жодною сторінкою крамниці. Можливо, сторінка переїхала або в посиланні є помилка.",
      shop: "Уся крамниця",
      makers: "Познайомитись із майстрами",
      home: "Головна",
      searchLead: "Або пошукайте річ за назвою.",
    },
    orderLookupNoEmail: "Введіть номер замовлення, який ви зберегли після оформлення, і пошту, яку вказували.",
  },
};

export type UiStrings = typeof strings.en;

export function tu(lang: Lang): UiStrings {
  return lang === "uk" ? (strings.uk as UiStrings) : strings.en;
}

/** The public path tells the language: English is unprefixed, Ukrainian is /uk. */
export function langFromPath(pathname: string | null | undefined): Lang {
  const p = pathname || "/";
  return p === "/uk" || p.startsWith("/uk/") ? "uk" : "en";
}

export default strings;

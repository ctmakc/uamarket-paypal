/**
 * Strings for the pre-purchase pages (FAQ, shipping, care, privacy, terms).
 *
 * web/lib/i18n.ts belongs to the orchestrator, so the chrome of these pages
 * lives here. The pages themselves carry no literal copy: everything a
 * customer reads comes either from this dictionary or from web/lib/content.ts.
 */
import type { Lang } from "@/lib/i18n";

const strings = {
  en: {
    index: "On this page",
    written: (date: string) => `Written ${date}`,
    draftNote: (contact: string | null): string =>
      contact
        ? "A figure marked \"not confirmed yet\" is our working proposal, and one marked \"not published yet\" has no value at all so far. Write to us before you rely on either."
        : "A figure marked \"not confirmed yet\" is our working proposal, and one marked \"not published yet\" has no value at all so far. This is a demonstration shop, so rely on neither.",
    confirmLine: (contact: string | null) =>
      contact ? `We'll confirm this before the shop opens. Questions: ${contact}` : "We'll confirm this before the shop opens.",
    stillHeading: "Still not answered",
    stillLead: "Write to the shop and add your order number to the subject line if you already have one.",
    stillNoEmail: "This is a demonstration shop, and its contact address is not published yet.",
    configMissing: "The shop's figures could not be loaded just now. Reload the page.",
  },
  uk: {
    index: "На цій сторінці",
    written: (date: string) => `Написано ${date}`,
    draftNote: (contact: string | null): string =>
      contact
        ? "Цифра з позначкою «ще не підтверджено» — наша робоча пропозиція, а там, де стоїть «ще не опубліковано», значення поки немає. Перш ніж на них покладатися, напишіть нам."
        : "Цифра з позначкою «ще не підтверджено» — наша робоча пропозиція, а там, де стоїть «ще не опубліковано», значення поки немає. Це демонстраційна крамниця, тож не покладайтеся ні на те, ні на інше.",
    confirmLine: (contact: string | null) =>
      contact ? `Ми підтвердимо це до відкриття крамниці. Питання: ${contact}` : "Ми підтвердимо це до відкриття крамниці.",
    stillHeading: "Залишилося питання",
    stillLead: "Напишіть у крамницю й вкажіть у темі листа номер замовлення, якщо він у вас уже є.",
    stillNoEmail: "Це демонстраційна крамниця, і її контактну адресу ще не опубліковано.",
    configMissing: "Зараз не вдалося завантажити цифри крамниці. Перезавантажте сторінку.",
  },
};

export type ContentStrings = typeof strings.en;

export function tc(lang: Lang): ContentStrings {
  return lang === "uk" ? (strings.uk as ContentStrings) : strings.en;
}

export default strings;

/**
 * Copy that depends on one fact: whether the shop can send email at all.
 *
 * The API reports it at /v1/storefront/config as `notifications`, which is true only when
 * SMTP is configured on the server. Checkout and the order page read it through
 * `mailNotice()` and pick their wording from here, so the shop promises a confirmation
 * email only while it can actually send one. When it cannot, the order page and the order
 * number are named as the record instead.
 */
import type { Lang } from "@/lib/i18n";

export type MailNotice = { email: boolean; from: string | null };

/** The safe reading of an unknown or unreachable config: no email is promised. */
export const MAIL_OFF: MailNotice = { email: false, from: null };

type ConfigWithNotifications = { notifications?: { email?: boolean; from_email?: string | null } };

/**
 * Read the notification block off the storefront config. The config type lives in
 * lib/api.ts, which this module does not own, so the shape is narrowed here instead.
 */
export function mailNotice(config: unknown): MailNotice {
  const block = (config as ConfigWithNotifications | null | undefined)?.notifications;
  if (!block || block.email !== true) return MAIL_OFF;
  return { email: true, from: typeof block.from_email === "string" && block.from_email ? block.from_email : null };
}

const en = {
  // checkout
  confirmTo: (from: string | null) =>
    from ? `A confirmation goes to this address from ${from}.` : "A confirmation goes to this address.",
  noEmailAtCheckout: "The shop sends no email yet. Keep the order number you get after placing the order — the order page carries the status.",
  payEtransferNoEmail: (recipient: string) =>
    `Send the total to ${recipient} with your order number as the message. The order page shows the payment once the shop confirms it.`,
  /**
   * The e-Transfer recipient is a placeholder the storefront blanks out (see
   * deliverableEmail in lib/api.ts), so there is no address to send money to.
   * Saying so beats printing "Send the total to ." with a hole in it.
   */
  payEtransferNoRecipient:
    "The shop has published no e-Transfer address yet, so an order placed now waits as unpaid until it does.",
  payInvoiceNoEmail: (contact: string | null) =>
    contact
      ? `Write to ${contact} to arrange payment. Keep your order number.`
      : "The shop has published no payment contact yet. Keep your order number.",
  // order page
  placedWithEmail: (address: string) => `The confirmation goes to ${address}. This page carries the current status.`,
  placedNoEmail: "Keep this order number. This page carries the current status.",
  paidNoEmail: "This page carries the current status.",
  orderPayEtransferNoEmail: (recipient: string, num: string, amount: string) =>
    `Send ${amount} by Interac e-Transfer to ${recipient}. Put ${num} in the message. This page shows the payment once the shop confirms it.`,
  orderPayEtransferNoRecipient: (num: string, amount: string) =>
    `${amount} is due for this order. The shop has published no e-Transfer address yet, so there is nowhere to send it. Keep ${num} — this page carries the state of the order.`,
  orderPayInvoiceNoEmail: (contact: string | null) =>
    contact
      ? `Write to ${contact} to arrange payment for this order.`
      : "The shop has published no payment contact yet. Keep this order number.",
};

const uk: typeof en = {
  confirmTo: (from: string | null) =>
    from ? `Підтвердження надійде на цю адресу з ${from}.` : "Підтвердження надійде на цю адресу.",
  noEmailAtCheckout: "Крамниця поки не надсилає листів. Збережіть номер замовлення, який побачите після оформлення, — стан показує сторінка замовлення.",
  payEtransferNoEmail: (recipient: string) =>
    `Надішліть суму на ${recipient}, у повідомленні вкажіть номер замовлення. Сторінка замовлення покаже оплату, щойно крамниця її підтвердить.`,
  payEtransferNoRecipient:
    "Крамниця ще не опублікувала адреси для Interac e-Transfer, тож замовлення, оформлене зараз, чекатиме неоплаченим, доки вона з'явиться.",
  payInvoiceNoEmail: (contact: string | null) =>
    contact
      ? `Напишіть на ${contact}, щоб домовитися про оплату. Збережіть номер замовлення.`
      : "Крамниця поки не вказала контакт для оплати. Збережіть номер замовлення.",
  placedWithEmail: (address: string) => `Підтвердження надійде на ${address}. Ця сторінка показує поточний стан.`,
  placedNoEmail: "Збережіть номер замовлення. Ця сторінка показує поточний стан.",
  paidNoEmail: "Ця сторінка показує поточний стан.",
  orderPayEtransferNoEmail: (recipient: string, num: string, amount: string) =>
    `Надішліть ${amount} через Interac e-Transfer на ${recipient}. У повідомленні вкажіть ${num}. Ця сторінка покаже оплату, щойно крамниця її підтвердить.`,
  orderPayEtransferNoRecipient: (num: string, amount: string) =>
    `До сплати ${amount}. Крамниця ще не опублікувала адреси для Interac e-Transfer, тож надсилати гроші нікуди. Збережіть ${num} — ця сторінка показує стан замовлення.`,
  orderPayInvoiceNoEmail: (contact: string | null) =>
    contact
      ? `Напишіть на ${contact}, щоб домовитися про оплату цього замовлення.`
      : "Крамниця поки не вказала контакт для оплати. Збережіть номер замовлення.",
};

export function tm(lang: Lang) {
  return lang === "uk" ? uk : en;
}

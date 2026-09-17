/**
 * Copy whose truth depends on the shop's settings.
 *
 * The home page and /about used to carry fixed sentences about delivery,
 * pickup and payment: "Canada Post from Ottawa", "Tracking number by email",
 * "A one-time code opens your bay. Pick up on your own schedule, day or
 * night.", "Interac e-Transfer or card". On this deployment the config says
 * `payment_methods: ["ETRANSFER"]` and `notifications.email: false`, and no
 * setting anywhere records the carrier or the hours a locker bay can be
 * reached — so one click apart the site promised card payment that checkout
 * does not offer and an email the checkout itself says it will not send.
 *
 * Every sentence here is a function of what the shop actually has switched on.
 * web/lib/i18n.ts belongs to the orchestrator, so these live in their own
 * module. Both languages, always together.
 */
import type { Lang } from "@/lib/i18n";

const strings = {
  en: {
    /** Heading of the shipping card, built from `shipPhrase()`. */
    shipTitle: (ship: string) => ship,
    shipSub: (flat: string, free: string, mail: boolean) =>
      `${flat} flat within Canada, free over ${free}. ${
        mail
          ? "The tracking number reaches you by email when the parcel is handed to the courier."
          : "The tracking number appears on your order page when the parcel is handed to the courier."
      }`,
    pickupSub: (hours: string | null) =>
      hours
        ? `A one-time code opens your bay, ${hours}. The address comes with the code.`
        : "A one-time code opens your bay, and the address comes with the code. The hours the bay can be reached are not published yet.",
    payTitle: (methods: string) => methods.charAt(0).toUpperCase() + methods.slice(1),
    payNone: "No payment method is switched on",
    payNoneSub: "The shop is not taking payments yet. We'll confirm how to pay before the shop opens.",
    /** /about, long form. */
    aboutShipping: (ship: string, flat: string, free: string, mail: boolean) =>
      `${ship}: ${flat} flat within Canada, free once the bag reaches ${free}. ${
        mail
          ? "The tracking number reaches you by email when the parcel is handed to the courier."
          : "The shop sends no email yet, so the tracking number appears on your order page when the parcel is handed to the courier."
      }`,
    aboutShippingUnknown: "Checkout prints the delivery amount before the order is placed.",
    aboutPickup: (hours: string | null) =>
      `Choose pickup at checkout. When the order is packed you receive a one-time code for a locker bay, and the address comes with the code.${
        hours ? ` The bay opens on that code ${hours}.` : " The hours the bay can be reached are not published yet."
      }`,
    aboutPayment: (methods: string) =>
      `The shop accepts ${methods}. An order is created as unpaid and waits for the money; nothing ships before it arrives, and an unpaid order can be cancelled from its status page.`,
    /** The home page's featured band. */
    featured: "The shop's pick",
    featuredSub: "Pieces the shop put at the front of the chart.",
    /**
     * /makers. The shared line said "Each one is a real place with a real
     * region on the tag", which is a claim about the workshops themselves; the
     * assortment on this deployment is seeded, so the page says what it can
     * show instead. Since 17.09 the lede also names the workshops as made up,
     * because "The workshops behind the shop" read as a claim that seven
     * businesses with those towns and founding years exist. Every place a
     * maker name appears carries the same mark: see components/ExampleMark.
     */
    makersSub: "The workshops here are made up, written to show the shop working. Every product page names its workshop and the region on its tag, and real workshops take these places once the shop opens.",
    /**
     * The order page for a pickup order. The fulfillment core issues the bay
     * code to the operator who packs the order and to nobody else — there is no
     * customer-facing access grant and no mail kind that carries a code — so
     * this page says where the code is not, instead of leaving a buyer waiting
     * for a message the software cannot send. See docs/OWNER-ACTIONS.md.
     */
    pickupCodePending: "The bay code and the address are not on this page. The shop passes them on once the order is packed.",
    /**
     * The checkout's delivery option. The shared label reads "Ship by Canada
     * Post", and the software never chooses a carrier — it reads one back off
     * the postage rate it buys — so a company is named only once the owner has
     * named it.
     */
    shipOption: (carrierName: string | null) => (carrierName ? `Ship by ${carrierName}` : "Ship to my address"),
  },
  uk: {
    shipTitle: (ship: string) => ship,
    shipSub: (flat: string, free: string, mail: boolean) =>
      `${flat} по Канаді, безкоштовно від ${free}. ${
        mail
          ? "Трек-номер надходить поштою, щойно посилку передано кур'єру."
          : "Трек-номер з'являється на сторінці вашого замовлення, щойно посилку передано кур'єру."
      }`,
    pickupSub: (hours: string | null) =>
      hours
        ? `Одноразовий код відкриває ваш бокс, ${hours}. Адреса приходить разом із кодом.`
        : "Одноразовий код відкриває ваш бокс, а адреса приходить разом із кодом. Години, коли до боксу можна дістатися, ще не опубліковано.",
    payTitle: (methods: string) => methods.charAt(0).toUpperCase() + methods.slice(1),
    payNone: "Жодного способу оплати не ввімкнено",
    payNoneSub: "Крамниця ще не приймає оплату. Як платити, ми підтвердимо до відкриття.",
    aboutShipping: (ship: string, flat: string, free: string, mail: boolean) =>
      `${ship}: ${flat} по Канаді, безкоштовно, щойно кошик сягає ${free}. ${
        mail
          ? "Трек-номер надходить вам поштою, щойно посилку передано кур'єру."
          : "Крамниця поки не надсилає листів, тож трек-номер з'являється на сторінці вашого замовлення, щойно посилку передано кур'єру."
      }`,
    aboutShippingUnknown: "Суму доставки сторінка оформлення друкує до підтвердження замовлення.",
    aboutPickup: (hours: string | null) =>
      `Оберіть самовивіз під час оформлення. Коли замовлення спаковане, ви отримуєте одноразовий код до боксу локера, а адреса приходить разом із кодом.${
        hours ? ` Бокс відкривається цим кодом ${hours}.` : " Години, коли до боксу можна дістатися, ще не опубліковано."
      }`,
    aboutPayment: (methods: string) =>
      `Крамниця приймає: ${methods}. Замовлення створюється неоплаченим і чекає на гроші; до їх надходження нічого не відправляється, а неоплачене замовлення можна скасувати на його сторінці стану.`,
    featured: "Вибір крамниці",
    featuredSub: "Речі, які крамниця поставила на початок схеми.",
    makersSub: "Майстерні тут вигадані, написані, щоб показати крамницю в роботі. Кожна сторінка товару називає свою майстерню й регіон із бирки, а справжні майстерні стануть на ці місця, коли крамниця відкриється.",
    pickupCodePending: "Коду до боксу й адреси на цій сторінці немає. Крамниця передає їх, щойно замовлення спаковане.",
    shipOption: (carrierName: string | null) => (carrierName ? `Доставка через ${carrierName}` : "Доставка на мою адресу"),
  },
};

export type FactStrings = typeof strings.en;

export function tf(lang: Lang): FactStrings {
  return lang === "uk" ? (strings.uk as FactStrings) : strings.en;
}

export default strings;

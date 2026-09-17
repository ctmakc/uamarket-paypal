/**
 * Strings for buying honestly: the demonstration strip, the "not taking orders yet" state,
 * the local test payment page, quantity clamps and the order page's payment notes.
 * Every entry exists in English and in Ukrainian and states only what the code does.
 */
import type { Lang } from "@/lib/i18n";

const strings = {
  en: {
    demoStrip: "Demonstration shop. The goods, makers and prices are sample data, and nothing here is for sale yet.",
    demoStripShort: "Demonstration shop: sample goods, nothing for sale yet.",
    demoAtCheckout: "This shop shows demonstration goods. An order placed here is a test; send no money for it.",
    closedTitle: "The shop is not taking orders yet",
    closedBody: "No payment method is set up, so an order placed now could not be paid. Your bag stays saved in this browser.",
    closedContact: (email: string) => `Questions: ${email}`,
    backToBag: "Back to the bag",
    payTest: "Card (test payment)",
    payTestSub: "A local test page stands in for the card form. It asks for no card and moves no money.",
    orderDemo: "This order was placed in a demonstration shop. Do not send money for it.",
    payTestButton: "Open the test payment page",
    retryPay: "Start a new card payment",
    retryFailed: "A new payment could not be started. The items may have sold out; write to the shop about this order.",
    clampReduce: "Fewer available; we set it to the most we can send.",
    clampSoldOut: "Sold out",
    lineShort: (title: string) => `${title}: fewer available than your bag holds. Return to the bag to adjust.`,
    lineSoldOut: (title: string) => `${title}: sold out. Remove it from the bag to place the order.`,
    testPage: {
      title: "Test payment",
      lede: "This page stands in for a card checkout while the shop is a demonstration. The button records the order as paid. No card details are asked for and no money moves.",
      order: "Order",
      amount: "Amount",
      pay: (amount: string) => `Pay ${amount} (test)`,
      paying: "Recording the payment…",
      paid: "Payment recorded.",
      toOrder: "Go to the order",
      missing: "This payment session does not exist or has closed.",
      failed: "The test payment could not be recorded. Try again.",
    },
  },
  uk: {
    demoStrip: "Демонстраційна крамниця. Товари, майстри й ціни тут — зразкові дані, і поки нічого не продається.",
    demoStripShort: "Демонстраційна крамниця: зразкові товари, поки нічого не продається.",
    demoAtCheckout: "Крамниця показує демонстраційні товари. Замовлення тут тестове; грошей за нього не надсилайте.",
    closedTitle: "Крамниця ще не приймає замовлень",
    closedBody: "Спосіб оплати ще не налаштовано, тож замовлення зараз не вдалося б оплатити. Кошик залишається збереженим у цьому браузері.",
    closedContact: (email: string) => `Питання: ${email}`,
    backToBag: "Назад до кошика",
    payTest: "Картка (тестова оплата)",
    payTestSub: "Замість форми картки відкриється локальна тестова сторінка. Дані картки вона не просить, гроші не рухаються.",
    orderDemo: "Це замовлення зроблено в демонстраційній крамниці. Не надсилайте за нього гроші.",
    payTestButton: "Відкрити тестову сторінку оплати",
    retryPay: "Почати нову оплату карткою",
    retryFailed: "Нову оплату почати не вдалося. Можливо, товари розпродано; напишіть у крамницю щодо цього замовлення.",
    clampReduce: "Доступно менше; ми поставили найбільшу кількість, яку можемо надіслати.",
    clampSoldOut: "Розпродано",
    lineShort: (title: string) => `${title}: доступно менше, ніж у кошику. Поверніться до кошика, щоб змінити кількість.`,
    lineSoldOut: (title: string) => `${title}: розпродано. Приберіть це з кошика, щоб оформити замовлення.`,
    testPage: {
      title: "Тестова оплата",
      lede: "Ця сторінка заміняє оплату карткою, поки крамниця працює як демонстрація. Кнопка позначає замовлення оплаченим. Даних картки не потрібно, гроші не рухаються.",
      order: "Замовлення",
      amount: "Сума",
      pay: (amount: string) => `Сплатити ${amount} (тест)`,
      paying: "Записуємо оплату…",
      paid: "Оплату записано.",
      toOrder: "До замовлення",
      missing: "Такої сесії оплати немає або її закрито.",
      failed: "Тестову оплату записати не вдалося. Спробуйте ще раз.",
    },
  },
};

export function to(lang: Lang) {
  return strings[lang] ?? strings.en;
}

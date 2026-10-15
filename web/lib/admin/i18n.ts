/** Operator copy, English and Ukrainian. Plain data, safe in client components. */
export type AdminLang = "en" | "uk";
export const ADMIN_LANG_COOKIE = "uam_admin_lang";

const en = {
  brand: "UA Market",
  admin: "Admin",
  nav: { orders: "Orders", products: "Products", makers: "Makers", stock: "Stock", locker: "Locker", import: "Import", paypal: "PayPal desk" },
  langSwitch: "Українською",
  signOut: "Sign out",
  login: {
    title: "Sign in to the shop",
    lede: "Orders, products and stock for UA Market.",
    password: "Password",
    submit: "Sign in",
    wrong: "That password is not right.",
    locked: (s: number) => `Too many wrong passwords. Sign-in is locked for ${Math.ceil(s / 60)} min.`,
    failed: "Sign-in failed. Try again.",
    notConfigured: "Admin sign-in is not set up on this server yet.",
    missing: "Missing settings:",
    howTo: "Generate the password hash and secret with: python3 tools/admin_password_hash.py",
  },
  common: {
    save: "Save", saved: "Saved", saving: "Saving…", cancel: "Cancel", back: "Back", edit: "Edit", close: "Close",
    retire: "Retire", unretire: "Bring back", delete: "Delete", search: "Search", en: "English", uk: "Українська",
    yes: "Yes", no: "No", none: "—", error: "Something went wrong", required: "required", all: "All",
    onSale: "On sale", notOnSale: "Not on sale", retired: "Retired", active: "Active", loading: "Loading…",
    demo: "Demo", preview: "Preview", open: "Open",
  },
  queue: {
    title: "Orders",
    tabs: { awaiting_payment: "Awaiting payment", to_pack: "To pack", ready_to_ship: "Ready to ship", shipped: "Shipped", exceptions: "Problems", cancelled: "Cancelled" },
    empty: "Nothing here.",
    searchPlaceholder: "Order number, name or email",
    paidToday: "Paid today",
    items: (n: number) => `${n} ${n === 1 ? "item" : "items"}`,
    other: "Other problems (not tied to one order)",
    next: { mark_paid: "Mark paid", await_card: "Waiting for card", reserve: "Reserve", scan: "Scan", pack: "Pack", ship: "Ship", locker: "Locker", none: "Done" },
    demoNote: "Demo orders are placed while the catalogue is placeholder. No money moves.",
  },
  order: {
    back: "Orders",
    placed: "Placed",
    next: "Next",
    steps: ["Placed", "Paid", "Reserved", "Scanned", "Packed", "Shipped"],
    markPaid: { title: "Record the e-Transfer", lede: "Check the bank first. The reference is what the bank shows.", ref: "Reference (optional)", button: "Mark e-Transfer received" },
    awaitCard: { title: "Waiting for card payment", lede: "The order is paid automatically when the card payment arrives." },
    reserve: { title: "Reserve the stock", lede: "Takes the items off the shelf count for this order.", button: "Reserve stock" },
    scan: {
      title: "Scan each item", lede: "Scan the barcode on each item, or type its barcode or SKU from the list below and press Enter.", placeholder: "Scan or type a barcode or SKU", button: "Check",
      ok: (sku: string) => `✓ ${sku} scanned`, left: (n: number) => `${n} left to scan`,
    },
    pack: { title: "Pack and weigh", lede: "Weigh the closed box.", weight: "Weight, grams", estimate: (g: number) => `Items alone weigh about ${g} g`, button: "Packed" },
    ship: {
      title: "Ship it", lede: "Type the carrier and the tracking number from the label.", carrier: "Carrier", tracking: "Tracking number",
      button: "Mark shipped", rates: "Get label rates", buy: "Buy this label", noLabel: "Label buying appears here once EasyPost and the ship-from address are set.",
    },
    locker: { title: "Locker pickup", lede: "This order leaves through the locker. Use the locker tools (API) for bay assignment." },
    done: { title: "Shipped", tracking: "Tracking" },
    cancelled: { title: "Cancelled" },
    items: "Items",
    picked: "scanned",
    notPicked: "not scanned",
    barcode: "Barcode",
    byHand: "Confirm by hand",
    byHandAsk: (sku: string) => `No scan for ${sku}. Have you checked this item by hand? The history will say it was confirmed by hand.`,
    shipTo: "Ship to",
    pickup: "Locker pickup",
    customer: "Customer",
    contact: { email: "Email", phone: "Phone", language: "Language" },
    payment: "Payment",
    buyerNote: "Note from the buyer",
    totals: { subtotal: "Subtotal", shipping: "Shipping", tax: "Tax", total: "Total" },
    timeline: "Timeline",
    emails: "Emails",
    mailState: { DELIVERED: "sent", SKIPPED: "not sent (email off)", PENDING: "sending", FAILED: "failed", NOT_SENT: "not sent yet" } as Record<string, string>,
    mailCaptured: "caught internally (demo, not delivered)",
    mailKind: { placed: "Order received", paid: "Payment received", handoff: "Shipped", pickup_ready: "In the locker", cancelled: "Cancelled" } as Record<string, string>,
    problems: "Problems",
    resolve: "Resolve",
    resolveNote: "What was done",
    resolved: "Resolved",
    addNote: "Add a note",
    notePlaceholder: "A call, a refund made, anything worth keeping",
    cancel: { title: "Cancel this order", note: "Reason (kept on the order)", button: "Cancel order", confirm: "Cancel the order? Paid orders open a refund reminder." },
    demo: "Demo order: no money should move for it.",
    method: { PAYPAL: "PayPal", STRIPE: "Card", ETRANSFER: "Interac e-Transfer", INVOICE: "Invoice" } as Record<string, string>,
    history: {
      placed: "Placed", paid: "Paid", email: "Email", scan: "Scanned", problem: "Problem", resolved: "Resolved",
      cancel: "Cancelled", handCheck: (sku: string, qty: string, who: string) => `Checked by hand, no scan: ${sku} ×${qty} (confirmed by ${who})`,
      event: { PICK_PLANNED: "Picking planned", PARCEL_READY: "Parcel ready", HANDOFF_COMPLETE: "Handed to the carrier", SHIPPED: "Shipped", PICKUP_CODE_ISSUED: "Pickup code issued", RESERVED: "Stock reserved", RELEASED: "Stock released" } as Record<string, string>,
      problemKind: { WRONG_SKU: "wrong item scanned", REFUND_DUE: "refund due", ORDER_EMAIL_FAILED: "email failed", OUT_OF_STOCK: "out of stock", PAID_OUT_OF_STOCK: "paid but out of stock", PAYMENT_AMOUNT_MISMATCH: "payment amount does not match", LABEL_FAIL: "label not bought", LABEL_BUY_UNRESOLVED: "label purchase unclear", PICKUP_NOT_CONFIGURED: "locker pickup not set up" } as Record<string, string>,
    },
  },
  products: {
    title: "Products", new: "New product", empty: "No products yet.", searchPlaceholder: "Title, address name or SKU",
    filter: { all: "All", active: "On sale", inactive: "Not on sale" },
    cols: { product: "Product", maker: "Maker", price: "Price", variants: "Variants", stock: "Available / on hand", status: "Status" },
    noPhoto: "no photo",
  },
  editor: {
    newTitle: "New product",
    text: "Text",
    facts: "Facts",
    fields: {
      title: "Title", subtitle: "Subtitle", description: "Description", technique: "Technique", material: "Material", care: "Care",
      origin_note: "Where and how it was made", slug: "Address name", category: "Category", collection: "Collection",
      origin: "How it was made", maker: "Maker", featured: "Show on the home page",
    },
    slugHint: "Letters a–z, digits and hyphens. Filled from the English title when empty.",
    create: "Create product",
    putOnSale: "Put on sale",
    takeOff: "Take off sale",
    problemsTitle: "Before it can go on sale",
    liveNote: "The catalogue is live: photos with alt text, stock and a size chart for garments are required.",
    placeholderNote: "The catalogue is still placeholder: price and weight are required now; photos, alt text, stock and size charts become required when it goes live.",
    preview: "Preview on the shop",
    previewHidden: "The shop shows it only once it is on sale.",
    variants: "Variants",
    variantCols: { sku: "SKU", label: "Label EN", labelUk: "Label UK", price: "Price CA$", weight: "Weight g", stock: "Available / on hand", barcode: "Barcode" },
    addVariant: "Add variant",
    variantMore: { cost: "Cost CA$", fibre: "Fibre content", country: "Country of origin", hs: "HS code", dims: "Parcel L × W × H, cm" },
    autoFill: "SKU and barcode fill themselves when left empty.",
    photos: "Photos",
    drop: "Drop photos here, or choose files",
    dropHint: "JPEG, PNG or WebP · up to 15 MB · the first photo is the one on the tile",
    choose: "Choose files",
    uploading: (name: string) => `Uploading ${name}…`,
    altEn: "Alt text EN", altUk: "Alt text UK", moveUp: "Earlier", moveDown: "Later",
    tooBig: (name: string, mb: string) => `“${name}” is ${mb} MB; the limit is 15 MB. Export a smaller JPEG and try again.`,
    badType: (name: string) => `“${name}” is not a photo the shop accepts. Use a JPEG, PNG or WebP file.`,
    sizeChart: "Size chart",
    sizeChartLede: "Measurements per size, exactly as the maker gives them. Empty uses the shop default.",
    sizeChartUsingDefault: "Using the shop default chart.",
    size: "Size", measure: "Measure", addSize: "Add size", addMeasure: "Add measure", unit: "Unit",
    receive: "Receive stock",
  },
  makers: {
    title: "Makers", new: "New maker", empty: "No makers yet.",
    fields: { name: "Name", region: "Region", craft: "Craft", story: "Story", country: "Country (2 letters)", founded_year: "Founded", slug: "Address name" },
    products: (n: number) => `${n} products`,
    create: "Create maker",
    /** The seeded catalogue's workshops are written, and the storefront says so on every card. */
    seeded: "Every workshop in this list is made up for the demonstration. Real workshops replace them from this screen.",
  },
  locker: {
    title: "Locker",
    lede: "What each bay reports and holds. Parcels go into a bay from the order page; doors are opened only by the locker's own device.",
    pickupOff: "Locker pickup is off at checkout: no pickup address is set (PICKUP_ADDRESS).",
    pickupOn: "Locker pickup is offered at checkout.",
    noBays: "No bays are set up yet. The locker is not connected.",
    cols: { bay: "Bay", sensors: "Gate and door", inside: "Inside", code: "Buyer code", courier: "Courier pickup" },
    enabled: "in service", disabled: "out of service",
    shut: "gate closed, door closed and locked", open: "open or unlocked",
    empty: "empty", codeLive: (until: string) => `live until ${until}`, noCode: "none",
    window: (a: string, b: string) => `${a} – ${b}`,
    devices: "Devices", noDevices: "No locker device has reported yet.", lastSeen: "last seen",
  },
  stock: {
    title: "Stock",
    lede: "Every change is a ledger entry. Shoppers see only “in stock”, “few left” or “sold out”.",
    searchPlaceholder: "SKU, barcode or product",
    cols: { product: "Product", sku: "SKU", onHand: "On hand", reserved: "Reserved", available: "Available", shopper: "Shopper sees" },
    shopper: { in: "In stock", low: "Few left", out: "Sold out" },
    receive: "Receive", adjust: "Adjust",
    qty: "Quantity", delta: "Change (+/−)", reason: "Reason", note: "Note", location: "Location",
    receiveButton: "Add to stock", adjustButton: "Record change",
    history: "History",
  },
  import: {
    title: "Import a sourcing sheet",
    lede: "One row per variant, CSV UTF-8. Check it first; nothing is written until you apply.",
    template: "Download the template",
    doc: "Column guide",
    choose: "Choose CSV file",
    check: "Check the sheet",
    apply: "Apply import",
    report: "Report",
    summary: (r: { products: { create: number; update: number }; variants: { create: number; update: number }; errors: number }) =>
      `Products: ${r.products.create} new, ${r.products.update} updated · Variants: ${r.variants.create} new, ${r.variants.update} updated · Errors: ${r.errors}`,
    applied: "Imported.",
    fixFirst: "Fix the rows with errors and check again; nothing was written.",
    line: "Row",
  },
};

export type AdminDict = typeof en;

const uk: AdminDict = {
  brand: "UA Market",
  admin: "Адмінка",
  nav: { orders: "Замовлення", products: "Товари", makers: "Майстри", stock: "Склад", locker: "Локер", import: "Імпорт", paypal: "PayPal" },
  langSwitch: "English",
  signOut: "Вийти",
  login: {
    title: "Вхід до крамниці",
    lede: "Замовлення, товари та склад UA Market.",
    password: "Пароль",
    submit: "Увійти",
    wrong: "Пароль неправильний.",
    locked: (s: number) => `Забагато неправильних паролів. Вхід заблоковано на ${Math.ceil(s / 60)} хв.`,
    failed: "Не вдалося увійти. Спробуйте ще раз.",
    notConfigured: "Вхід до адмінки на цьому сервері ще не налаштовано.",
    missing: "Бракує налаштувань:",
    howTo: "Згенеруйте хеш пароля та секрет: python3 tools/admin_password_hash.py",
  },
  common: {
    save: "Зберегти", saved: "Збережено", saving: "Зберігаємо…", cancel: "Скасувати", back: "Назад", edit: "Змінити", close: "Закрити",
    retire: "Зняти", unretire: "Повернути", delete: "Видалити", search: "Пошук", en: "English", uk: "Українська",
    yes: "Так", no: "Ні", none: "—", error: "Щось пішло не так", required: "обов'язково", all: "Усі",
    onSale: "У продажу", notOnSale: "Не в продажу", retired: "Знято", active: "Активний", loading: "Завантаження…",
    demo: "Демо", preview: "Перегляд", open: "Відкрити",
  },
  queue: {
    title: "Замовлення",
    tabs: { awaiting_payment: "Чекають оплати", to_pack: "Пакувати", ready_to_ship: "До відправки", shipped: "Відправлено", exceptions: "Проблеми", cancelled: "Скасовано" },
    empty: "Тут порожньо.",
    searchPlaceholder: "Номер замовлення, ім'я чи email",
    paidToday: "Оплачено сьогодні",
    items: (n: number) => `${n} ${n % 10 === 1 && n % 100 !== 11 ? "річ" : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? "речі" : "речей"}`,
    other: "Інші проблеми (не прив'язані до замовлення)",
    next: { mark_paid: "Позначити оплату", await_card: "Чекаємо картку", reserve: "Зарезервувати", scan: "Сканувати", pack: "Пакувати", ship: "Відправити", locker: "Локер", none: "Готово" },
    demoNote: "Демо-замовлення створюються, поки каталог демонстраційний. Гроші не рухаються.",
  },
  order: {
    back: "Замовлення",
    placed: "Створено",
    next: "Далі",
    steps: ["Створено", "Оплачено", "Резерв", "Скановано", "Запаковано", "Відправлено"],
    markPaid: { title: "Зарахувати e-Transfer", lede: "Спершу перевірте банк. Референс — те, що показує банк.", ref: "Референс (необов'язково)", button: "E-Transfer отримано" },
    awaitCard: { title: "Чекаємо оплату карткою", lede: "Замовлення стане оплаченим саме, щойно надійде платіж." },
    reserve: { title: "Зарезервувати товар", lede: "Знімає речі з вільного залишку під це замовлення.", button: "Зарезервувати" },
    scan: {
      title: "Скануйте кожну річ", lede: "Скануйте штрихкод на кожній речі або введіть її штрихкод чи SKU зі списку нижче й натисніть Enter.", placeholder: "Штрихкод або SKU", button: "Перевірити",
      ok: (sku: string) => `✓ ${sku} скановано`, left: (n: number) => `Лишилося сканувати: ${n}`,
    },
    pack: { title: "Запакувати й зважити", lede: "Зважте закриту коробку.", weight: "Вага, грами", estimate: (g: number) => `Самі речі важать близько ${g} г`, button: "Запаковано" },
    ship: {
      title: "Відправити", lede: "Введіть перевізника й трек-номер з етикетки.", carrier: "Перевізник", tracking: "Трек-номер",
      button: "Позначити відправленим", rates: "Тарифи на етикетку", buy: "Купити цю етикетку", noLabel: "Купівля етикеток з'явиться тут, коли буде налаштовано EasyPost та адресу відправлення.",
    },
    locker: { title: "Самовивіз із локера", lede: "Це замовлення видається через локер. Комірку призначають інструментами локера (API)." },
    done: { title: "Відправлено", tracking: "Трек-номер" },
    cancelled: { title: "Скасовано" },
    items: "Речі",
    picked: "скановано",
    notPicked: "не скановано",
    barcode: "Штрихкод",
    byHand: "Підтвердити вручну",
    byHandAsk: (sku: string) => `${sku} не скановано. Ви перевірили цю річ вручну? В історії буде записано, що її підтверджено вручну.`,
    shipTo: "Доставка",
    pickup: "Самовивіз із локера",
    customer: "Покупець",
    contact: { email: "Email", phone: "Телефон", language: "Мова" },
    payment: "Оплата",
    buyerNote: "Примітка покупця",
    totals: { subtotal: "Товари", shipping: "Доставка", tax: "Податок", total: "Разом" },
    timeline: "Історія",
    emails: "Листи",
    mailState: { DELIVERED: "надіслано", SKIPPED: "не надіслано (пошта вимкнена)", PENDING: "надсилається", FAILED: "помилка", NOT_SENT: "ще не надіслано" },
    mailCaptured: "перехоплено (демо, не доставлено)",
    mailKind: { placed: "Замовлення прийнято", paid: "Оплату отримано", handoff: "Відправлено", pickup_ready: "У локері", cancelled: "Скасовано" },
    problems: "Проблеми",
    resolve: "Закрити",
    resolveNote: "Що зроблено",
    resolved: "Закрито",
    addNote: "Додати примітку",
    notePlaceholder: "Дзвінок, повернення коштів, усе, що варто зберегти",
    cancel: { title: "Скасувати замовлення", note: "Причина (зберігається в замовленні)", button: "Скасувати замовлення", confirm: "Скасувати замовлення? Для оплачених з'явиться нагадування про повернення коштів." },
    demo: "Демо-замовлення: гроші за нього не мають рухатися.",
    method: { PAYPAL: "PayPal", STRIPE: "Картка", ETRANSFER: "Interac e-Transfer", INVOICE: "Рахунок" },
    history: {
      placed: "Оформлено", paid: "Оплачено", email: "Лист", scan: "Скановано", problem: "Проблема", resolved: "Закрито",
      cancel: "Скасовано", handCheck: (sku: string, qty: string, who: string) => `Перевірено вручну, без сканування: ${sku} ×${qty} (підтвердив ${who})`,
      event: { PICK_PLANNED: "Збирання заплановано", PARCEL_READY: "Посилка готова", HANDOFF_COMPLETE: "Передано перевізнику", SHIPPED: "Відправлено", PICKUP_CODE_ISSUED: "Видано код самовивозу", RESERVED: "Товар зарезервовано", RELEASED: "Резерв знято" },
      problemKind: { WRONG_SKU: "відскановано не ту річ", REFUND_DUE: "треба повернути кошти", ORDER_EMAIL_FAILED: "лист не надіслано", OUT_OF_STOCK: "немає в наявності", PAID_OUT_OF_STOCK: "оплачено, але немає в наявності", PAYMENT_AMOUNT_MISMATCH: "сума оплати не збігається", LABEL_FAIL: "етикетку не куплено", LABEL_BUY_UNRESOLVED: "купівля етикетки під питанням", PICKUP_NOT_CONFIGURED: "самовивіз не налаштовано" },
    },
  },
  products: {
    title: "Товари", new: "Новий товар", empty: "Товарів ще немає.", searchPlaceholder: "Назва, адреса чи SKU",
    filter: { all: "Усі", active: "У продажу", inactive: "Не в продажу" },
    cols: { product: "Товар", maker: "Майстер", price: "Ціна", variants: "Варіанти", stock: "Вільно / на полиці", status: "Стан" },
    noPhoto: "без фото",
  },
  editor: {
    newTitle: "Новий товар",
    text: "Тексти",
    facts: "Дані",
    fields: {
      title: "Назва", subtitle: "Підзаголовок", description: "Опис", technique: "Техніка", material: "Матеріал", care: "Догляд",
      origin_note: "Де і як зроблено", slug: "Адреса сторінки", category: "Категорія", collection: "Колекція",
      origin: "Як зроблено", maker: "Майстер", featured: "Показувати на головній",
    },
    slugHint: "Латинські літери, цифри й дефіси. Якщо порожньо — з англійської назви.",
    create: "Створити товар",
    putOnSale: "Виставити в продаж",
    takeOff: "Зняти з продажу",
    problemsTitle: "Щоб виставити в продаж, бракує",
    liveNote: "Каталог живий: потрібні фото з описом, товар на складі й таблиця розмірів для одягу.",
    placeholderNote: "Каталог ще демонстраційний: зараз потрібні ціна й вага; фото, описи фото, залишок і таблиці розмірів стануть обов'язковими, коли каталог запрацює.",
    preview: "Переглянути в крамниці",
    previewHidden: "Крамниця показує товар, лише коли він у продажу.",
    variants: "Варіанти",
    variantCols: { sku: "SKU", label: "Назва EN", labelUk: "Назва UK", price: "Ціна CA$", weight: "Вага г", stock: "Вільно / на полиці", barcode: "Штрихкод" },
    addVariant: "Додати варіант",
    variantMore: { cost: "Собівартість CA$", fibre: "Склад тканини", country: "Країна походження", hs: "Код HS", dims: "Посилка Д × Ш × В, см" },
    autoFill: "SKU і штрихкод заповняться самі, якщо лишити порожніми.",
    photos: "Фото",
    drop: "Перетягніть фото сюди або виберіть файли",
    dropHint: "JPEG, PNG або WebP · до 15 МБ · перше фото показується на плитці",
    choose: "Вибрати файли",
    uploading: (name: string) => `Завантажуємо ${name}…`,
    altEn: "Опис фото EN", altUk: "Опис фото UK", moveUp: "Раніше", moveDown: "Пізніше",
    tooBig: (name: string, mb: string) => `«${name}» важить ${mb} МБ; межа — 15 МБ. Збережіть менший JPEG і спробуйте ще раз.`,
    badType: (name: string) => `«${name}» — не той тип фото. Завантажте JPEG, PNG або WebP.`,
    sizeChart: "Таблиця розмірів",
    sizeChartLede: "Мірки для кожного розміру, як їх дає майстер. Порожня — діє загальна таблиця крамниці.",
    sizeChartUsingDefault: "Діє загальна таблиця крамниці.",
    size: "Розмір", measure: "Мірка", addSize: "Додати розмір", addMeasure: "Додати мірку", unit: "Одиниці",
    receive: "Прийняти товар",
  },
  makers: {
    title: "Майстри", new: "Новий майстер", empty: "Майстрів ще немає.",
    fields: { name: "Назва", region: "Регіон", craft: "Ремесло", story: "Історія", country: "Країна (2 літери)", founded_year: "Рік заснування", slug: "Адреса сторінки" },
    products: (n: number) => `товарів: ${n}`,
    create: "Створити майстра",
    seeded: "Усі майстерні в цьому списку вигадані для демонстрації. Справжні майстерні замінюють їх із цього екрана.",
  },
  locker: {
    title: "Локер",
    lede: "Що показує і що містить кожна комірка. Посилку кладуть у комірку зі сторінки замовлення; двері відчиняє лише пристрій локера.",
    pickupOff: "Самовивіз із локера вимкнено на оформленні: адресу самовивозу не задано (PICKUP_ADDRESS).",
    pickupOn: "Самовивіз із локера пропонується на оформленні.",
    noBays: "Комірок ще немає. Локер не під'єднано.",
    cols: { bay: "Комірка", sensors: "Засувка і двері", inside: "Усередині", code: "Код покупця", courier: "Кур'єр" },
    enabled: "працює", disabled: "вимкнена",
    shut: "засувку закрито, двері зачинено й замкнено", open: "відчинено або незамкнено",
    empty: "порожньо", codeLive: (until: string) => `діє до ${until}`, noCode: "немає",
    window: (a: string, b: string) => `${a} – ${b}`,
    devices: "Пристрої", noDevices: "Жоден пристрій локера ще не виходив на зв'язок.", lastSeen: "востаннє",
  },
  stock: {
    title: "Склад",
    lede: "Кожна зміна — запис у журналі. Покупці бачать лише «є», «лишилося мало» чи «розпродано».",
    searchPlaceholder: "SKU, штрихкод чи товар",
    cols: { product: "Товар", sku: "SKU", onHand: "На полиці", reserved: "У резерві", available: "Вільно", shopper: "Бачить покупець" },
    shopper: { in: "Є", low: "Мало", out: "Розпродано" },
    receive: "Прийняти", adjust: "Виправити",
    qty: "Кількість", delta: "Зміна (+/−)", reason: "Причина", note: "Примітка", location: "Місце",
    receiveButton: "Додати на склад", adjustButton: "Записати зміну",
    history: "Журнал",
  },
  import: {
    title: "Імпорт таблиці закупівлі",
    lede: "Один рядок — один варіант, CSV UTF-8. Спершу перевірка; нічого не записується, доки не застосуєте.",
    template: "Завантажити шаблон",
    doc: "Опис колонок",
    choose: "Вибрати CSV",
    check: "Перевірити таблицю",
    apply: "Застосувати імпорт",
    report: "Звіт",
    summary: (r) => `Товари: нових ${r.products.create}, оновлено ${r.products.update} · Варіанти: нових ${r.variants.create}, оновлено ${r.variants.update} · Помилок: ${r.errors}`,
    applied: "Імпортовано.",
    fixFirst: "Виправте рядки з помилками й перевірте знову; нічого не записано.",
    line: "Рядок",
  },
};

export function adminDict(lang: AdminLang): AdminDict {
  return lang === "uk" ? uk : en;
}

export function pickLang(lang: AdminLang, en: string | null | undefined, ukText: string | null | undefined): string {
  return lang === "uk" && ukText ? ukText : en || "";
}

export function adminMoney(value: number | null | undefined): string {
  return `CA$ ${Number(value ?? 0).toFixed(2)}`;
}

export function adminTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || /[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

export type TimelineEvent = { at: string | null; kind: string; text: string; author?: string; code?: string; params?: Record<string, string> };

/** One history line in the admin's language; falls back to the API's English text for anything unknown. */
export function mailStateText(state: string, lang: AdminLang, captured = false): string {
  const o = adminDict(lang).order;
  return captured && state === "DELIVERED" ? o.mailCaptured : o.mailState[state] || state;
}

export function timelineText(t: TimelineEvent, lang: AdminLang, mailCaptured = false): string {
  const h = adminDict(lang).order.history;
  const o = adminDict(lang).order;
  const p = t.params || {};
  const q = (x: string) => (lang === "uk" ? `«${x}»` : `“${x}”`);
  switch (t.code) {
    case "placed":
      return `${h.placed} · ${o.method[p.method] || p.method || ""}`.trim();
    case "paid":
      return `${h.paid} · ${o.method[p.method] || p.method || ""} ${p.ref || ""}`.trim();
    case "email":
      return `${h.email} ${q(o.mailKind[p.mail] || p.mail)} · ${mailStateText(p.state, lang, mailCaptured)}`;
    case "event":
      return h.event[p.event] || t.text;
    case "scan":
      return `${h.scan} ${p.barcode || ""}`.trim();
    case "problem":
      return `${h.problem}: ${h.problemKind[p.problem] || p.problem}`;
    case "resolved":
      return `${h.resolved} ${q(h.problemKind[p.problem] || p.problem)}${p.note ? `: ${p.note}` : ""}`;
    case "hand_check":
      return h.handCheck(p.sku, p.qty, p.author);
    case "cancel":
      return `${h.cancel}: ${t.text}`;
    default:
      return t.text;
  }
}

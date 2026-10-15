export type Photo = { id: string; src: string; srcset: string; width: number; height: number; alt: string; alt_uk: string; position: number };
export type Problem = { code: string; message: string; message_uk: string; sku?: string };
export type StockCell = { on_hand: number; reserved: number; available: number; shopper?: { in_stock: boolean; low: boolean }; locations: { location_id: string; kind: string; sellable: boolean; on_hand: number; reserved: number }[] };
export type AdminVariant = {
  id: string; sku: string; barcode: string; option_label: string | null; option_label_uk: string | null; price_cad: number;
  cost_cad: number | null; weight_g: number | null; length_cm: number | null; width_cm: number | null; height_cm: number | null;
  fibre_content: string | null; country_of_origin: string | null; hs_code: string | null; active: boolean; position: number; stock: StockCell;
};
export type SizeChart = { unit: "cm" | "in"; note?: string; note_uk?: string; rows: Record<string, Record<string, string>> };
export type AdminProductSummary = {
  id: string; slug: string; title: string; title_uk: string | null; category: string; collection: string; origin: string; active: boolean;
  featured: boolean; maker: { id: string; slug: string; name: string; name_uk: string | null } | null; price_from_cad: number | null;
  price_to_cad: number | null; variant_count: number; on_hand: number; available: number; thumb: Photo | null; photo_count: number; position: number;
};
export type AdminProduct = AdminProductSummary & {
  subtitle: string | null; subtitle_uk: string | null; description: string; description_uk: string | null; origin_note: string | null;
  origin_note_uk: string | null; technique: string | null; technique_uk: string | null; material: string | null; material_uk: string | null;
  care: string | null; care_uk: string | null; size_chart: SizeChart | null; size_chart_effective: SizeChart | null;
  variants: AdminVariant[]; images: Photo[]; problems: Problem[]; catalogue_live: boolean;
};
export type AdminMaker = {
  id: string; slug: string; name: string; name_uk: string | null; region: string; region_uk: string | null; country: string; craft: string;
  craft_uk: string | null; story: string; story_uk: string | null; image_url: string | null; founded_year: number | null; active: boolean;
  position: number; product_count: number;
};
export type Taxonomy = {
  categories: { slug: string; title: string; title_uk: string; garment: boolean; active: boolean }[];
  collections: { slug: string; title: string; title_uk: string; active: boolean }[];
  origins: { id: string; label: string; label_uk: string }[];
  locations: { id: string; kind: string; sellable: boolean }[];
  adjust_reasons: { id: string; label: string; label_uk: string }[];
  size_chart_default: SizeChart | null;
};
export type QueueName = "awaiting_payment" | "to_pack" | "ready_to_ship" | "shipped" | "exceptions" | "cancelled";
export type OrderSummary = {
  id: string; order_number: string; channel: string; state: string; queue: string; created_at: string | null; paid_at: string | null;
  customer_name: string | null; customer_email: string | null; city: string | null; province: string | null; fulfillment_method: string | null;
  payment_method: string | null; total_cad: number; items: number; demo: boolean; has_exception: boolean;
};
export type ExceptionRow = {
  id: string; kind: string; state: string; reference_type: string; reference_id: string; summary: string; details: string;
  created_at: string | null; resolution_note: string | null; resolved_by: string | null; resolved_at: string | null;
};
export type NextKind = "mark_paid" | "await_card" | "reserve" | "scan" | "pack" | "ship" | "locker" | "none";
export type OrderDetail = OrderSummary & {
  customer: { name: string | null; email: string | null; phone: string | null; locale: string | null };
  ship_to: Record<string, string>;
  note: string;
  totals: { subtotal_cad: number | null; shipping_cad: number | null; tax_cad: number | null; tax_rate: number | null; total_cad: number };
  payment: { method: string | null; reference: string | null; paid_at: string | null; hold_expires_at: string | null;
    paypal?: { order_id: string | null; capture_id: string | null; status: string | null; tracking_id: string | null; refund_id: string | null; sandbox: boolean; refundable: boolean } | null };
  lines: {
    id: string; sku: string | null; barcode: string | null; label: string | null; label_uk: string | null; title: string; title_uk: string | null; product_id: string | null;
    qty: number; unit_price_cad: number; line_total_cad: number; photo: { src: string; srcset: string; alt: string; alt_uk: string } | null;
    weight_g: number | null; missions: { id: string; state: string; qty: number; location: string; scanned: string | null }[]; picked: boolean;
  }[];
  package: { id: string; state: string; weight_g: number | null } | null;
  estimated_weight_g: number | null;
  shipment: { provider: string; state: string; carrier: string | null; tracking_code: string | null; label_url: string | null } | null;
  exceptions: ExceptionRow[];
  next: { kind: NextKind; secondary: string[] };
  timeline: { at: string | null; kind: string; text: string; author?: string; code?: string; params?: Record<string, string> }[];
  mail: { kind: string; state: string; subject: string | null }[];
  /** True when mail goes to a local catcher (demo): nothing reaches the buyer. */
  mail_captured?: boolean;
  label: { available: boolean; api_key: boolean; ship_from: boolean };
};

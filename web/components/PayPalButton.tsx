"use client";

/**
 * The PayPal button, PayPal JS SDK v6 (web components, no SDK npm package).
 *
 * The SDK script loads once per page from the URL the API names (sandbox or live). On click
 * the button starts a one-time payment session with a *promise* for the PayPal order id —
 * the order is created on the shop's server inside that promise, priced from the database,
 * and the popup opens in the same click so the browser's transient activation is not lost.
 * onApprove hands the id back to the shop's server, which captures and checks the amount.
 */
import { useEffect, useRef, useState } from "react";
import type { PayPalConfig } from "@/lib/api";

type Session = { start: (opts: { presentationMode: string }, order: Promise<{ orderId: string }>) => Promise<void> };
type Instance = {
  findEligibleMethods: (o: { currencyCode: string }) => Promise<{ isEligible: (m: string) => boolean }>;
  createPayPalOneTimePaymentSession: (o: {
    onApprove: (d: { orderId: string }) => Promise<void> | void;
    onCancel?: (d: { orderId?: string }) => void;
    onError?: (e: Error) => void;
  }) => Session;
};
type PayPalGlobal = { createInstance: (o: { clientId: string; components: string[]; pageType?: string; locale?: string }) => Promise<Instance> };

declare global {
  interface Window { paypal?: PayPalGlobal }
}

declare module "react" {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      "paypal-button": React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & { type?: string; class?: string };
    }
  }
}

const scripts = new Map<string, Promise<PayPalGlobal>>();
const instances = new Map<string, Promise<Instance>>();

function loadSdk(url: string): Promise<PayPalGlobal> {
  if (!scripts.has(url)) {
    scripts.set(url, new Promise((resolve, reject) => {
      if (window.paypal) return resolve(window.paypal);
      const el = document.createElement("script");
      el.src = url;
      el.async = true;
      el.onload = () => (window.paypal ? resolve(window.paypal) : reject(new Error("PayPal SDK did not start")));
      el.onerror = () => { scripts.delete(url); reject(new Error("PayPal SDK could not be loaded")); };
      document.head.appendChild(el);
    }));
  }
  return scripts.get(url)!;
}

function instanceFor(cfg: PayPalConfig, lang: "en" | "uk"): Promise<Instance> {
  const key = `${cfg.sdk_url}|${cfg.client_id}|${lang}`;
  if (!instances.has(key)) {
    instances.set(key, loadSdk(cfg.sdk_url).then((pp) =>
      pp.createInstance({ clientId: cfg.client_id, components: ["paypal-payments"], pageType: "checkout", locale: lang === "uk" ? "uk-UA" : "en-CA" })));
  }
  return instances.get(key)!;
}

export type PayPalButtonProps = {
  config: PayPalConfig;
  lang: "en" | "uk";
  /** Creates (or reuses) the shop order and its PayPal order; resolves to the PayPal order id. */
  createOrder: () => Promise<string>;
  /** The buyer approved in PayPal: capture on the server. */
  onApproved: (paypalOrderId: string) => Promise<void>;
  onCancel?: () => void;
  onError?: (message: string) => void;
  /** While true the button is shown but does nothing (terms box unticked, form invalid). */
  disabled?: boolean;
  /** Called on click while disabled, so the form can say why. */
  onBlocked?: () => void;
  describedBy?: string;
};

export default function PayPalButton({ config, lang, createOrder, onApproved, onCancel, onError, disabled, onBlocked, describedBy }: PayPalButtonProps) {
  const holder = useRef<HTMLDivElement>(null);
  const session = useRef<Session | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "unavailable">("loading");
  const latest = useRef({ createOrder, onApproved, onCancel, onError, disabled, onBlocked });
  latest.current = { createOrder, onApproved, onCancel, onError, disabled, onBlocked };

  useEffect(() => {
    let alive = true;
    instanceFor(config, lang)
      .then(async (sdk) => {
        const methods = await sdk.findEligibleMethods({ currencyCode: config.currency || "CAD" });
        if (!alive) return;
        if (!methods.isEligible("paypal")) { setState("unavailable"); return; }
        session.current = sdk.createPayPalOneTimePaymentSession({
          onApprove: async ({ orderId }) => { await latest.current.onApproved(orderId); },
          onCancel: () => latest.current.onCancel?.(),
          onError: (e) => latest.current.onError?.(e?.message || "PayPal error"),
        });
        setState("ready");
      })
      .catch(() => { if (alive) setState("unavailable"); });
    return () => { alive = false; };
  }, [config, lang]);

  useEffect(() => {
    const el = holder.current?.querySelector("paypal-button");
    if (!el) return;
    const click = async () => {
      if (latest.current.disabled) { latest.current.onBlocked?.(); return; }
      if (!session.current) return;
      // Not awaited before start(): the popup must open inside this click.
      const order = latest.current.createOrder().then((orderId) => ({ orderId }));
      order.catch(() => undefined);
      try {
        await session.current.start({ presentationMode: "auto" }, order);
      } catch (e) {
        latest.current.onError?.(e instanceof Error ? e.message : "PayPal error");
      }
    };
    el.addEventListener("click", click);
    return () => el.removeEventListener("click", click);
  }, [state]);

  if (state === "unavailable") {
    return <p className="error" role="alert" data-paypal-unavailable>{lang === "uk" ? "PayPal зараз недоступний. Спробуйте за хвилину." : "PayPal is not available right now. Try again in a minute."}</p>;
  }
  return (
    <div ref={holder} className="paypal-slot" data-paypal-state={state} data-disabled={disabled ? "true" : "false"} aria-describedby={describedBy}>
      {state === "loading" ? <p className="mono mono--sm muted">{lang === "uk" ? "Завантажуємо PayPal…" : "Loading PayPal…"}</p> : null}
      <paypal-button type="pay" hidden={state !== "ready"} data-paypal-button />
    </div>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import { adminGet } from "@/lib/admin/api";
import { adminDict, adminTime } from "@/lib/admin/i18n";
import { adminLang } from "@/lib/admin/server";
import { requireSession } from "@/lib/admin/session";

export const metadata: Metadata = { title: "Locker" };

type LockerBay = {
  id: string; carrier_group: string; enabled: boolean; weight_g: number;
  inner_gate_closed: boolean; outer_door_closed: boolean; outer_door_locked: boolean;
  parcels: { package_id: string; state: string; order_id: string; order_number: string | null }[];
  customer_codes: { order_id: string; valid_until: string | null }[];
  courier_pickups: { id: string; carrier: string; state: string; window_start: string | null; window_end: string | null }[];
};
type LockerData = { pickup_configured: boolean; bays: LockerBay[]; devices: { id: string; kind: string; state: string; last_seen_at: string | null }[] };

/** Read-only locker overview: sensors, parcels, whether a buyer code is live, courier windows. */
export default async function LockerPage() {
  await requireSession();
  const lang = await adminLang();
  const l = adminDict(lang).locker;
  const data = await adminGet<LockerData>("/v1/admin/lockers");
  return (
    <>
      <div className="adm-head">
        <div>
          <h1 className="h1">{l.title}</h1>
          <p className="muted" style={{ fontSize: "var(--fs-ui)" }}>{l.lede}</p>
        </div>
      </div>
      <p style={{ marginBottom: "calc(var(--st) * 2)" }} data-testid="locker-pickup">
        <span className={`adm-status adm-status--${data.pickup_configured ? "ok" : "quiet"}`}>{data.pickup_configured ? l.pickupOn : l.pickupOff}</span>
      </p>
      {data.bays.length === 0 ? (
        <p className="adm-empty" data-testid="locker-empty">{l.noBays}</p>
      ) : (
        <div className="adm-scroll">
          <table className="adm-table adm-table--stack" data-testid="locker-table">
            <thead>
              <tr>
                <th scope="col">{l.cols.bay}</th>
                <th scope="col">{l.cols.sensors}</th>
                <th scope="col">{l.cols.inside}</th>
                <th scope="col">{l.cols.code}</th>
                <th scope="col">{l.cols.courier}</th>
              </tr>
            </thead>
            <tbody>
              {data.bays.map((b) => {
                const shut = b.inner_gate_closed && b.outer_door_closed && b.outer_door_locked;
                return (
                  <tr key={b.id} data-bay={b.id}>
                    <td className="wide">
                      <strong className="mono">{b.id}</strong>
                      <span className="muted" style={{ display: "block", fontSize: "var(--fs-ui)" }}>
                        {b.carrier_group} · <span className={`adm-status adm-status--${b.enabled ? "ok" : "bad"}`}>{b.enabled ? l.enabled : l.disabled}</span>
                      </span>
                    </td>
                    <td data-label={l.cols.sensors}>
                      <span className={`adm-status adm-status--${shut ? "ok" : "wait"}`}>{shut ? l.shut : l.open}</span>
                    </td>
                    <td data-label={l.cols.inside}>
                      {b.parcels.length === 0 ? <span className="muted">{l.empty}</span> : b.parcels.map((p) => (
                        <span key={p.package_id} style={{ display: "block" }}>
                          <Link className="adm-link mono" href={`/admin/orders/${p.order_id}`}>{p.order_number || p.order_id.slice(0, 8)}</Link>
                          <span className="muted mono mono--sm"> {b.weight_g} g</span>
                        </span>
                      ))}
                    </td>
                    <td data-label={l.cols.code}>
                      {b.customer_codes.length === 0 ? <span className="muted">{l.noCode}</span> : b.customer_codes.map((c) => (
                        <span key={c.order_id} style={{ display: "block" }}>{l.codeLive(adminTime(c.valid_until))}</span>
                      ))}
                    </td>
                    <td data-label={l.cols.courier}>
                      {b.courier_pickups.length === 0 ? <span className="muted">—</span> : b.courier_pickups.map((c) => (
                        <span key={c.id} style={{ display: "block" }}>{c.carrier} · {l.window(adminTime(c.window_start), adminTime(c.window_end))}</span>
                      ))}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <section className="adm-section" style={{ marginTop: "calc(var(--st) * 4)" }}>
        <h2 className="adm-section__title">{l.devices}</h2>
        {data.devices.length === 0 ? <p className="adm-empty">{l.noDevices}</p> : (
          <ul className="adm-sheet" style={{ listStyle: "none" }}>
            {data.devices.map((dv) => (
              <li key={dv.id} className="mono">{dv.id} · {dv.kind} · <span className={`adm-status adm-status--${dv.state === "ONLINE" ? "ok" : "wait"}`}>{dv.state}</span> · {l.lastSeen} {adminTime(dv.last_seen_at)}</li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

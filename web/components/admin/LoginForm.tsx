"use client";

import { useRef, useState } from "react";
import { adminDict, type AdminLang } from "@/lib/admin/i18n";

export default function LoginForm({ lang }: { lang: AdminLang }) {
  const d = adminDict(lang).login;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    const password = input.current?.value || "";
    try {
      const res = await fetch("/admin/api/login", {
        method: "POST",
        headers: { "content-type": "application/json", "x-admin-login": "1" },
        body: JSON.stringify({ password }),
        credentials: "same-origin",
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok) {
        window.location.assign(body.next || "/admin");
        return;
      }
      if (res.status === 429) setError(d.locked(Number(body.retry_after) || 900));
      else if (res.status === 401) setError(d.wrong);
      else setError(d.failed);
      if (input.current) {
        input.current.value = "";
        input.current.focus();
      }
    } catch {
      setError(d.failed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="adm-login__form" onSubmit={submit} noValidate>
      <label className="field">
        <span className="field__label">{d.password}</span>
        <input
          ref={input}
          className="input"
          type="password"
          name="password"
          autoComplete="current-password"
          required
          autoFocus
          aria-invalid={error ? "true" : undefined}
          aria-describedby="login-error"
        />
      </label>
      <p id="login-error" className="error" role="alert" aria-live="assertive" style={{ minHeight: 24 }}>{error}</p>
      <button className="btn btn--red btn--lg btn--wide" type="submit" disabled={busy}>{d.submit}</button>
    </form>
  );
}

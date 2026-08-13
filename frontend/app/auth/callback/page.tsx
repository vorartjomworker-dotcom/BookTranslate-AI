"use client";

import { useEffect, useState } from "react";
import { setApiToken } from "../../lib/api";

export default function AuthCallbackPage() {
  const [message, setMessage] = useState("Completing sign-in…");

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const token = params.get("token") ?? "";
    if (!token) {
      setMessage("Sign-in did not return an application token.");
      return;
    }
    setApiToken(token);
    setMessage("Signed in. Redirecting…");
    window.setTimeout(() => window.location.replace("/"), 250);
  }, []);

  return <main className="shell"><div className="panel loading-panel">{message}</div></main>;
}

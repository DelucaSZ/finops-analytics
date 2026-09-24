"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { MfaSettings } from "@/components/mfa-settings";
import { api } from "@/lib/api";

export default function MfaSetupPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  return <main className="mfa-enrollment"><h1>Proteja sua conta DeepOps</h1>
    <MfaSettings enrollment />
    {error && <p role="alert" className="form-error">{error}</p>}
    <button className="button" onClick={async () => {
      try { await api("/auth/logout", { method: "POST" }); router.replace("/login"); }
      catch (err) { setError(err instanceof Error ? err.message : "Não foi possível sair."); }
    }}>Sair</button>
  </main>;
}

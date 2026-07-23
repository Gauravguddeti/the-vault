"use client";
import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

type DocDetail = {
  id: string; original_name: string; status: string; mime_type: string;
  file_size: number; raw_text: string; error_message?: string;
  created_at: string; updated_at: string;
  amount?: number; currency?: string; txn_date?: string;
  vendor?: string; category?: string;
};

const fmt = (bytes: number) => bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(0)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

export default function DocumentDetailPage() {
  const { data: session } = useSession();
  const router = useRouter();
  const params = useParams();
  const id = params.id as string;
  const token = (session as any)?.accessToken || "";

  const [doc, setDoc] = useState<DocDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [showRaw, setShowRaw] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!session) return;
    fetch(`${BACKEND}/api/documents/${id}`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json()).then(setDoc).catch(() => {}).finally(() => setLoading(false));
  }, [session, id, token]);

  async function handleDelete() {
    if (!confirm("Delete this document? All chunks and extracted data will be removed.")) return;
    setDeleting(true);
    await fetch(`${BACKEND}/api/documents/${id}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
    router.push("/dashboard");
  }

  if (loading) return (
    <div className="flex items-center justify-center h-full">
      <div className="spinner" style={{ width: 28, height: 28, borderWidth: 3 }} />
    </div>
  );
  if (!doc) return (
    <div className="flex flex-col items-center justify-center h-full">
      <p style={{ color: "var(--text-muted)" }}>Document not found.</p>
      <Link href="/dashboard" className="btn-ghost mt-4">← Back to dashboard</Link>
    </div>
  );

  const fields = [
    { label: "Vendor", value: doc.vendor },
    { label: "Amount", value: doc.amount != null ? `${doc.amount}${doc.currency ? " " + doc.currency : ""}` : null },
    { label: "Date", value: doc.txn_date },
    { label: "Category", value: doc.category },
  ].filter(f => f.value);

  return (
    <div className="px-6 py-8 max-w-4xl mx-auto animate-fade-in">
      {/* Back */}
      <Link href="/dashboard" className="inline-flex items-center gap-2 text-sm mb-6 transition-colors"
        style={{ color: "var(--text-muted)" }}
        onMouseEnter={e => (e.currentTarget as HTMLElement).style.color = "var(--accent-light)"}
        onMouseLeave={e => (e.currentTarget as HTMLElement).style.color = "var(--text-muted)"}>
        ← Back to dashboard
      </Link>

      {/* Header */}
      <div className="glass rounded-2xl p-6 mb-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-4 min-w-0">
            <div className="w-12 h-12 rounded-xl flex-shrink-0 flex items-center justify-center"
              style={{ background: "var(--surface-3)" }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#818cf8" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
              </svg>
            </div>
            <div className="min-w-0">
              <h1 className="text-xl font-bold truncate">{doc.original_name}</h1>
              <div className="flex flex-wrap items-center gap-3 mt-2">
                <span className={`badge badge-${doc.status === "ready" ? "ready" : doc.status === "failed" ? "failed" : "processing"}`}>
                  {doc.status}
                </span>
                {doc.file_size && <span className="text-sm" style={{ color: "var(--text-muted)" }}>{fmt(doc.file_size)}</span>}
                <span className="text-sm" style={{ color: "var(--text-muted)" }}>Uploaded {new Date(doc.created_at).toLocaleDateString()}</span>
              </div>
            </div>
          </div>
          <button onClick={handleDelete} disabled={deleting}
            className="flex-shrink-0 px-4 py-2 rounded-xl text-sm font-medium transition-all"
            style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", color: "#f87171" }}
            onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = "rgba(239,68,68,0.2)"}
            onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = "rgba(239,68,68,0.1)"}>
            {deleting ? "Deleting…" : "Delete"}
          </button>
        </div>
      </div>

      {/* Extracted fields */}
      {fields.length > 0 && (
        <div className="glass rounded-2xl p-6 mb-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider mb-4" style={{ color: "var(--text-muted)" }}>Extracted Information</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {fields.map(f => (
              <div key={f.label} className="rounded-xl p-4" style={{ background: "var(--surface-2)" }}>
                <p className="text-xs font-medium mb-1" style={{ color: "var(--text-muted)" }}>{f.label}</p>
                <p className="font-semibold text-sm capitalize">{f.value}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Error */}
      {doc.error_message && (
        <div className="rounded-xl p-4 mb-6 text-sm" style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", color: "#f87171" }}>
          <strong>Processing error:</strong> {doc.error_message}
        </div>
      )}

      {/* Raw text */}
      {doc.raw_text && (
        <div className="glass rounded-2xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>Extracted Text</h2>
            <button onClick={() => setShowRaw(!showRaw)} className="btn-ghost text-xs py-1 px-3">
              {showRaw ? "Collapse" : "Expand"}
            </button>
          </div>
          <pre className={`text-sm leading-relaxed whitespace-pre-wrap overflow-auto transition-all ${showRaw ? "" : "max-h-48"}`}
            style={{ color: "var(--text-secondary)", fontFamily: "monospace", fontSize: "0.8rem" }}>
            {doc.raw_text}
          </pre>
        </div>
      )}

      {!doc.raw_text && doc.status !== "failed" && (
        <div className="glass rounded-2xl p-8 text-center">
          <div className="spinner mx-auto mb-3" style={{ width: 24, height: 24 }} />
          <p style={{ color: "var(--text-muted)" }}>Processing your document…</p>
        </div>
      )}
    </div>
  );
}

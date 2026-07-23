"use client";
import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { deleteDocument, renameDocument } from "@/lib/api";

type Doc = {
  id: string; original_name: string; status: string;
  mime_type: string; file_size: number; created_at: string;
};

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

const StatusBadge = ({ status }: { status: string }) => {
  const cls = { pending: "badge-pending", ocr_processing: "badge-processing", embedding: "badge-processing", ready: "badge-ready", failed: "badge-failed" }[status] ?? "badge-pending";
  const dot = { pending: "🟡", ocr_processing: "🔵", embedding: "🔵", ready: "🟢", failed: "🔴" }[status] ?? "⚪";
  const label = { pending: "Pending", ocr_processing: "OCR…", embedding: "Embedding…", ready: "Ready", failed: "Failed" }[status] ?? status;
  return <span className={`badge ${cls}`}>{dot} {label}</span>;
};

const fmt = (bytes: number) => bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(0)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

export default function DashboardPage() {
  const { data: session } = useSession();
  const router = useRouter();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [loading, setLoading] = useState(true);
  const [editId, setEditId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");

  const token = (session as any)?.accessToken || "";

  const fetchDocs = useCallback(async () => {
    if (!session) return;
    try {
      const res = await fetch(`${BACKEND}/api/documents`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setDocs(await res.json());
    } catch {}
    setLoading(false);
  }, [session, token]);

  useEffect(() => { fetchDocs(); }, [fetchDocs]);

  // Poll every 3s if any doc is not ready/failed
  useEffect(() => {
    const hasPending = docs.some(d => !["ready", "failed"].includes(d.status));
    if (!hasPending) return;
    const id = setInterval(fetchDocs, 3000);
    return () => clearInterval(id);
  }, [docs, fetchDocs]);

  async function handleDelete(id: string, name: string) {
    if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
    try {
      await fetch(`${BACKEND}/api/documents/${id}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
      setDocs(d => d.filter(x => x.id !== id));
    } catch { alert("Delete failed."); }
  }

  async function handleRename(id: string) {
    if (!editName.trim()) return;
    try {
      await fetch(`${BACKEND}/api/documents/${id}`, {
        method: "PATCH", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ original_name: editName }),
      });
      setDocs(d => d.map(x => x.id === id ? { ...x, original_name: editName } : x));
      setEditId(null);
    } catch { alert("Rename failed."); }
  }

  return (
    <div className="px-6 py-8 max-w-5xl mx-auto animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">Your Documents</h1>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            {docs.length} document{docs.length !== 1 ? "s" : ""} in your vault
          </p>
        </div>
        <Link href="/upload" className="btn-primary flex items-center gap-2">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Upload
        </Link>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <div className="text-center">
            <div className="spinner mx-auto mb-3" style={{ width: 28, height: 28, borderWidth: 3 }} />
            <p style={{ color: "var(--text-muted)" }}>Loading your vault…</p>
          </div>
        </div>
      ) : docs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center animate-fade-in">
          <div className="w-20 h-20 rounded-2xl flex items-center justify-center mb-6"
            style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#4f46e5" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/>
            </svg>
          </div>
          <h2 className="text-lg font-semibold mb-2">Your vault is empty</h2>
          <p className="mb-6" style={{ color: "var(--text-muted)", maxWidth: 320 }}>
            Upload your first document — receipts, invoices, PDFs — and start asking questions about them.
          </p>
          <Link href="/upload" className="btn-primary">Upload your first document</Link>
        </div>
      ) : (
        <div className="space-y-3">
          {docs.map(doc => (
            <div key={doc.id} className="glass glass-hover rounded-xl p-4 flex items-center gap-4 animate-slide-up group">
              {/* File icon */}
              <div className="flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center"
                style={{ background: "var(--surface-3)" }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#818cf8" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
                </svg>
              </div>

              {/* Name + meta */}
              <div className="flex-1 min-w-0">
                {editId === doc.id ? (
                  <div className="flex items-center gap-2">
                    <input className="input-field py-1 text-sm" value={editName} onChange={e => setEditName(e.target.value)}
                      onKeyDown={e => { if (e.key === "Enter") handleRename(doc.id); if (e.key === "Escape") setEditId(null); }}
                      autoFocus />
                    <button onClick={() => handleRename(doc.id)} className="btn-primary py-1 px-3 text-xs">Save</button>
                    <button onClick={() => setEditId(null)} className="btn-ghost py-1 px-3 text-xs">Cancel</button>
                  </div>
                ) : (
                  <Link href={`/documents/${doc.id}`} className="font-medium truncate block hover:text-indigo-400 transition-colors">
                    {doc.original_name}
                  </Link>
                )}
                <div className="flex items-center gap-3 mt-1">
                  <StatusBadge status={doc.status} />
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {doc.file_size ? fmt(doc.file_size) : ""} · {new Date(doc.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button title="Rename" onClick={() => { setEditId(doc.id); setEditName(doc.original_name); }}
                  className="p-2 rounded-lg hover:bg-surface-2 transition-colors" style={{ color: "var(--text-muted)" }}>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
                <button title="Delete" onClick={() => handleDelete(doc.id, doc.original_name)}
                  className="p-2 rounded-lg transition-colors" style={{ color: "var(--text-muted)" }}
                  onMouseEnter={e => (e.currentTarget as HTMLElement).style.color = "#f87171"}
                  onMouseLeave={e => (e.currentTarget as HTMLElement).style.color = "var(--text-muted)"}>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

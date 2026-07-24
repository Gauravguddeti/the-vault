"use client";
import { useState, useEffect } from "react";
import { IngestStatus } from "@/lib/useDocumentIngest";

interface ConfirmUploadModalProps {
  status: IngestStatus;
  progress: number;
  document: any;
  error: string | null;
  duplicateWarning?: string | null;
  onConfirm: (fields: any) => void;
  onCancel: () => void;
  isOpen: boolean;
}

export default function ConfirmUploadModal({
  status,
  progress,
  document,
  error,
  duplicateWarning,
  onConfirm,
  onCancel,
  isOpen,
}: ConfirmUploadModalProps) {
  const [fields, setFields] = useState({
    title: "",
    category: "",
    date: "",
    vendor: "",
    amount: "",
  });

  // Pre-fill fields when document is ready for confirmation
  useEffect(() => {
    if (document && status === "awaiting_confirmation") {
      setFields({
        title: document.original_name || "",
        category: document.category || "",
        date: document.txn_date || "",
        vendor: document.vendor || "",
        amount: document.amount?.toString() || "",
      });
    }
  }, [document, status]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-fade-in">
      <div className="bg-[var(--surface-1)] border border-[var(--border)] rounded-2xl p-6 w-full max-w-md shadow-2xl relative flex flex-col max-h-[90vh]">
        
        <h2 className="text-xl font-bold mb-4">
          {status === "uploading" ? "Uploading Document..." : 
           status === "analyzing" ? "Analyzing Document..." : 
           status === "awaiting_confirmation" ? "Confirm Details" :
           status === "confirming" ? "Finalizing Upload..." :
           status === "ready" ? "Upload Complete!" : "Upload"}
        </h2>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 text-red-500 rounded-lg text-sm">
            {error}
          </div>
        )}

        {(status === "uploading" || status === "analyzing" || status === "confirming") && (
          <div className="flex flex-col items-center justify-center py-8 space-y-4">
            <div className="w-12 h-12 border-4 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
            <p className="text-[var(--text-secondary)] text-sm">
              {status === "uploading" ? `Uploading... ${progress}%` :
               status === "analyzing" ? "Extracting text and identifying fields..." : 
               "Indexing for search..."}
            </p>
          </div>
        )}

        {status === "awaiting_confirmation" && (
          <div className="flex flex-col gap-4 overflow-y-auto pr-2">
            {duplicateWarning && (
              <div className="px-3 py-2 rounded-lg text-sm"
                style={{ background: "rgba(234,179,8,0.1)", border: "1px solid rgba(234,179,8,0.3)", color: "#facc15" }}>
                ⚠️ {duplicateWarning}
              </div>
            )}
            <div>
              <label className="block text-sm text-[var(--text-secondary)] mb-1">Title</label>
              <input
                type="text"
                className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-[var(--text-primary)]"
                value={fields.title}
                onChange={e => setFields({ ...fields, title: e.target.value })}
              />
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-[var(--text-secondary)] mb-1">Category</label>
                <input
                  type="text"
                  className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-[var(--text-primary)]"
                  value={fields.category}
                  onChange={e => setFields({ ...fields, category: e.target.value })}
                  placeholder="e.g. Receipt"
                />
              </div>
              <div>
                <label className="block text-sm text-[var(--text-secondary)] mb-1">Date</label>
                <input
                  type="date"
                  className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-[var(--text-primary)]"
                  value={fields.date}
                  onChange={e => setFields({ ...fields, date: e.target.value })}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-[var(--text-secondary)] mb-1">Vendor</label>
                <input
                  type="text"
                  className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-[var(--text-primary)]"
                  value={fields.vendor}
                  onChange={e => setFields({ ...fields, vendor: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-sm text-[var(--text-secondary)] mb-1">Amount</label>
                <input
                  type="number"
                  step="0.01"
                  className="w-full bg-[var(--surface-2)] border border-[var(--border)] rounded-lg px-3 py-2 text-[var(--text-primary)]"
                  value={fields.amount}
                  onChange={e => setFields({ ...fields, amount: e.target.value })}
                />
              </div>
            </div>
            
            <p className="text-xs text-[var(--text-muted)] mt-2 italic">
              These fields were auto-detected by AI. Please correct them if necessary.
            </p>

            <div className="flex justify-end gap-3 mt-4 pt-4 border-t border-[var(--border)]">
              <button onClick={onCancel} className="px-4 py-2 rounded-lg text-sm text-[var(--text-secondary)] hover:bg-[var(--surface-2)] transition-colors">
                Cancel
              </button>
              <button 
                onClick={() => onConfirm({ ...fields, amount: fields.amount ? parseFloat(fields.amount) : null })}
                className="px-4 py-2 rounded-lg text-sm bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
              >
                Confirm & Add to Vault
              </button>
            </div>
          </div>
        )}

        {status === "ready" && (
          <div className="flex flex-col items-center justify-center py-6 space-y-4">
            <div className="w-16 h-16 bg-green-500/20 text-green-500 rounded-full flex items-center justify-center">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            </div>
            <p className="text-center text-[var(--text-secondary)]">
              Added to your Vault successfully.
            </p>
            <button onClick={onCancel} className="mt-4 px-6 py-2 rounded-lg text-sm bg-[var(--surface-2)] hover:bg-[var(--surface-3)] transition-colors">
              Close
            </button>
          </div>
        )}
        
        {/* Simple close button for cancel during upload/analyze */}
        {(status === "uploading" || status === "analyzing" || status === "error") && (
          <button onClick={onCancel} className="absolute top-4 right-4 text-[var(--text-muted)] hover:text-white">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}

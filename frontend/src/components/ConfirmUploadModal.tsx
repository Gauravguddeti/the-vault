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
  onAutoConfirm: () => void;
  onCancel: () => void;
  /** Closes the modal WITHOUT resetting upload state. Used by "Do it yourself!" during analysis. */
  onDismiss: () => void;
  isOpen: boolean;
}

export default function ConfirmUploadModal({
  status,
  progress,
  document,
  error,
  duplicateWarning,
  onConfirm,
  onAutoConfirm,
  onCancel,
  onDismiss,
  isOpen,
}: ConfirmUploadModalProps) {
  const [fields, setFields] = useState({
    title: "",
    category: "",
    date: "",
    vendor: "",
    amount: "",
  });
  const [autoConfirmRequested, setAutoConfirmRequested] = useState(false);

  // Reset local state when modal opens/closes
  useEffect(() => {
    if (!isOpen) setAutoConfirmRequested(false);
  }, [isOpen]);

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

  // Fire global event when upload is complete so dashboard refreshes instantly
  useEffect(() => {
    if (status === "ready") {
      window.dispatchEvent(new Event("vault-upload-complete"));
    }
  }, [status]);

  if (!isOpen) return null;

  const handleAutoConfirm = () => {
    // This tells the backend hook to automatically submit as soon as the real document fields are ready.
    onAutoConfirm();
  };

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
            {/* "Do it yourself!" — dismisses modal immediately. Processing continues in background.
                The document card on the dashboard shows live status (Embedding… → Ready) via polling. */}
            {(status === "analyzing") && (
              <button
                onClick={() => {
                  onAutoConfirm();  // set autoConfirmRef = true so hook auto-submits when ready
                  onDismiss();      // hide modal only — do NOT reset ingest state
                }}
                className="mt-2 text-xs font-bold px-4 py-2 rounded-lg transition-all active:scale-95"
                style={{ 
                  background: "rgba(99,102,241,0.15)", 
                  border: "1px solid rgba(99,102,241,0.3)", 
                  color: "#818cf8",
                }}>
                Do it yourself! →
              </button>
            )}
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

            {/* Auto-confirm shortcut */}
            <div className="flex items-center gap-3 px-4 py-3 rounded-xl"
              style={{ background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.2)" }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#818cf8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
              </svg>
              <p className="text-xs flex-1" style={{ color: "var(--text-secondary)" }}>
                AI detected all fields. Trust it and add instantly.
              </p>
              <button
                id="auto-confirm-btn"
                onClick={handleAutoConfirm}
                className="flex-shrink-0 text-xs font-bold px-3 py-1.5 rounded-lg transition-all active:scale-95"
                style={{ background: "rgba(99,102,241,0.2)", border: "1px solid rgba(99,102,241,0.4)", color: "#818cf8" }}>
                Do it yourself!
              </button>
            </div>

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
              These fields were auto-detected by AI. Correct any mistakes above, then confirm.
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
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            </div>
            <p className="font-semibold text-[var(--text-primary)]">Added to your Vault!</p>
            <p className="text-sm text-center text-[var(--text-secondary)]">
              It's indexed and ready to query in the chat.
            </p>
            <button onClick={onCancel} className="mt-4 px-6 py-2 rounded-lg text-sm bg-[var(--surface-2)] hover:bg-[var(--surface-3)] transition-colors">
              Close
            </button>
          </div>
        )}
        
        {/* Close/cancel button visible on ALL non-ready states */}
        {status !== "ready" && status !== "awaiting_confirmation" && (
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

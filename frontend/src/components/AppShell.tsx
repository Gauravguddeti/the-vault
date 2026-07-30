"use client";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { signOut, useSession } from "next-auth/react";
import { useState, useRef, useCallback, useEffect } from "react";
import { useDocumentIngest } from "@/lib/useDocumentIngest";
import ConfirmUploadModal from "@/components/ConfirmUploadModal";
import { compressImage } from "@/lib/imageUtils";
import { ToastContainer, toast } from "@/components/ui/Toast";

// Offline queue stored in localStorage
const OFFLINE_QUEUE_KEY = "vault-offline-queue";

const navItems = [
  {
    href: "/chat", label: "Ask Vault", icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    )
  },
  {
    href: "/upload", label: "Upload", icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" />
        <line x1="12" y1="3" x2="12" y2="15" />
      </svg>
    )
  },
  {
    href: "/dashboard", label: "Your Vault", icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" />
        <rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" />
      </svg>
    )
  },
  {
    href: "/settings", label: "Settings", icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    )
  },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { data: session } = useSession();
  const token = (session as any)?.accessToken || "";

  // Global drag-drop state
  const [globalDragging, setGlobalDragging] = useState(false);
  // Pre-confirm dialog state (shown before kicking off the expensive ingest pipeline)
  const [preConfirmFile, setPreConfirmFile] = useState<File | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const dragCounter = useRef(0);

  // Scanner state
  const [scanPages, setScanPages] = useState<File[]>([]);
  const [scannerOpen, setScannerOpen] = useState(false);
  const scanInputRef = useRef<HTMLInputElement>(null);
  const [offlineQueueCount, setOfflineQueueCount] = useState(0);
  const [isOnline, setIsOnline] = useState(true);

  const ingest = useDocumentIngest(token);

  // Online/offline tracking
  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      processOfflineQueue();
    };
    const handleOffline = () => setIsOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    setIsOnline(navigator.onLine);
    readOfflineQueueCount();
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [token]);

  function readOfflineQueueCount() {
    try {
      const raw = localStorage.getItem(OFFLINE_QUEUE_KEY);
      const q = raw ? JSON.parse(raw) : [];
      setOfflineQueueCount(q.length);
    } catch { }
  }

  async function processOfflineQueue() {
    if (!token) return;
    try {
      const raw = localStorage.getItem(OFFLINE_QUEUE_KEY);
      const queue: { name: string; type: string; dataUrl: string }[] = raw ? JSON.parse(raw) : [];
      if (queue.length === 0) return;

      for (const item of queue) {
        // Convert data URL back to File
        const res = await fetch(item.dataUrl);
        const blob = await res.blob();
        const file = new File([blob], item.name, { type: item.type });
        // Upload directly (no confirmation for offline-queued files)
        const { uploadDocument } = await import("@/lib/api");
        await uploadDocument(file, token, false);
      }
      localStorage.removeItem(OFFLINE_QUEUE_KEY);
      setOfflineQueueCount(0);
    } catch (e) {
      console.error("Failed to process offline queue:", e);
    }
  }

  async function queueOffline(file: File) {
    return new Promise<void>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const raw = localStorage.getItem(OFFLINE_QUEUE_KEY);
          const q: any[] = raw ? JSON.parse(raw) : [];
          q.push({ name: file.name, type: file.type, dataUrl: reader.result as string });
          localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(q));
          setOfflineQueueCount(q.length);
        } catch { }
        resolve();
      };
      reader.readAsDataURL(file);
    });
  }

  // Global drag-drop handlers
  const onGlobalDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current++;
    if (e.dataTransfer.items.length > 0) setGlobalDragging(true);
  }, []);

  const onGlobalDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current--;
    if (dragCounter.current === 0) setGlobalDragging(false);
  }, []);

  const onGlobalDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current = 0;
    setGlobalDragging(false);

    // Don't intercept drops on the upload page — it has its own handler
    if (pathname.startsWith("/upload")) return;

    let file = e.dataTransfer.files[0];
    if (!file) return;
    
    if (file.type.startsWith("image/")) {
      file = await compressImage(file);
    }

    if (!isOnline) {
      await queueOffline(file);
      return;
    }

    // Show simple Yes/No before kicking off the pipeline
    setPreConfirmFile(file);
  }, [isOnline, ingest, token, pathname]);

  // Scanner logic
  function openScanner() {
    setScannerOpen(true);
    setScanPages([]);
  }

  function addScanPage(file: File) {
    setScanPages(prev => [...prev, file]);
  }

  async function finalizeScan() {
    if (scanPages.length === 0) return;
    setScannerOpen(false);

    let fileToUpload: File;

    if (scanPages.length === 1) {
      fileToUpload = scanPages[0];
    } else {
      // Multi-page: combine into a single PDF-like archive
      // For MVP: use the first page as the primary upload, then name it to suggest multi-page
      // A proper implementation would bundle into a PDF using pdf-lib
      const combinedName = `scan-${scanPages.length}-pages-${Date.now()}.jpg`;
      fileToUpload = new File([scanPages[0]], combinedName, { type: scanPages[0].type });
    }

    if (!isOnline) {
      await queueOffline(fileToUpload);
      setModalOpen(false);
      return;
    }

    setModalOpen(true);
    ingest.reset();
    ingest.startIngest(fileToUpload);
  }

  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ background: "var(--surface-0)" }}
      onDragEnter={onGlobalDragEnter}
      onDragLeave={onGlobalDragLeave}
      onDragOver={e => e.preventDefault()}
      onDrop={onGlobalDrop}
    >
      {/* Pre-confirm dialog: slide up from bottom on mobile, centered on desktop */}
      {preConfirmFile && (
        <>
          {/* Backdrop */}
          <div className="bottom-sheet-backdrop" onClick={() => setPreConfirmFile(null)} />
          {/* Bottom sheet on mobile / centered dialog on md+ */}
          <div className="md:hidden bottom-sheet">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.3)" }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#818cf8" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
                </svg>
              </div>
              <div className="min-w-0">
                <p className="font-semibold text-sm truncate">{preConfirmFile.name}</p>
                <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{(preConfirmFile.size / 1024).toFixed(0)} KB</p>
              </div>
            </div>
            <p className="text-sm mb-5" style={{ color: "var(--text-secondary)" }}>Add this file to your Vault?</p>
            <div className="flex gap-3">
              <button
                onClick={() => setPreConfirmFile(null)}
                className="flex-1 px-4 py-3 rounded-xl text-sm font-medium btn-press min-h-[44px]"
                style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                Not now
              </button>
              <button
                onClick={() => {
                  const f = preConfirmFile;
                  setPreConfirmFile(null);
                  setModalOpen(true);
                  ingest.reset();
                  ingest.startIngest(f);
                }}
                className="flex-1 px-4 py-3 rounded-xl text-sm font-bold btn-press min-h-[44px] btn-primary">
                Add to Vault
              </button>
            </div>
          </div>
          {/* Desktop-style centered dialog */}
          <div className="hidden md:flex fixed inset-0 z-50 items-center justify-center p-4 animate-fade-in">
            <div className="bg-[var(--surface-1)] border border-[var(--border)] rounded-2xl p-6 w-full max-w-sm shadow-2xl animate-scale-in">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                  style={{ background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.3)" }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#818cf8" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
                  </svg>
                </div>
                <div className="min-w-0">
                  <p className="font-semibold text-sm truncate">{preConfirmFile.name}</p>
                  <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{(preConfirmFile.size / 1024).toFixed(0)} KB</p>
                </div>
              </div>
              <p className="text-sm mb-5" style={{ color: "var(--text-secondary)" }}>Add this file to your Vault?</p>
              <div className="flex gap-3">
                <button
                  onClick={() => setPreConfirmFile(null)}
                  className="flex-1 px-4 py-2.5 rounded-xl text-sm font-medium btn-press"
                  style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                  Not now
                </button>
                <button
                  onClick={() => {
                    const f = preConfirmFile;
                    setPreConfirmFile(null);
                    setModalOpen(true);
                    ingest.reset();
                    ingest.startIngest(f);
                  }}
                  className="flex-1 px-4 py-2.5 rounded-xl text-sm font-bold btn-press btn-primary">
                  Add to Vault
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Global drag-drop overlay */}
      {globalDragging && (
        <div className="fixed inset-0 z-[999] flex flex-col items-center justify-center pointer-events-none"
          style={{ background: "rgba(99,102,241,0.12)", border: "3px dashed #6366f1" }}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#818cf8" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          <p className="text-indigo-300 font-semibold text-xl mt-4">Drop anywhere to add to Vault</p>
        </div>
      )}

      {/* Offline queue indicator */}
      {offlineQueueCount > 0 && (
        <div className="fixed top-4 right-4 z-50 px-3 py-2 rounded-lg text-xs font-medium"
          style={{ background: "rgba(234,179,8,0.15)", border: "1px solid rgba(234,179,8,0.3)", color: "#facc15" }}>
          {offlineQueueCount} file{offlineQueueCount > 1 ? "s" : ""} queued — upload will resume when online
        </div>
      )}

      {/* Sidebar */}
      <aside className="hidden md:flex flex-col w-64 flex-shrink-0"
        style={{ background: "var(--surface-1)", borderRight: "1px solid var(--border)" }}>
        <div className="flex items-center gap-3 px-6 py-5" style={{ borderBottom: "1px solid var(--border)" }}>
          <div className="flex items-center justify-center w-9 h-9 rounded-xl flex-shrink-0"
            style={{ background: "var(--accent)", boxShadow: "0 4px 0 #8a000e" }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
          </div>
          <span className="font-bold text-lg gradient-text">The Vault</span>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map(item => {
            const active = pathname.startsWith(item.href);
            return (
              <Link key={item.href} href={item.href}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150"
                style={{
                  background: active ? "rgba(99,102,241,0.15)" : "transparent",
                  color: active ? "#818cf8" : "var(--text-secondary)",
                  border: active ? "1px solid rgba(99,102,241,0.25)" : "1px solid transparent",
                }}>
                {item.icon}
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="px-3 pb-4" style={{ borderTop: "1px solid var(--border)", paddingTop: "12px" }}>
          <div className="px-3 py-2 mb-1">
            <p className="text-xs font-medium truncate" style={{ color: "var(--text-secondary)" }}>
              {session?.user?.email}
            </p>
          </div>
          <button onClick={() => signOut({ callbackUrl: "/login" })}
            className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm transition-all"
            style={{ color: "var(--text-muted)" }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = "#f87171"; (e.currentTarget as HTMLElement).style.background = "rgba(239,68,68,0.08)"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = "var(--text-muted)"; (e.currentTarget as HTMLElement).style.background = "transparent"; }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            Sign out
          </button>
        </div>
      </aside>

      {/* Mobile top bar */}
      <div className="md:hidden fixed top-0 inset-x-0 z-50 flex items-center justify-between px-4 h-14"
        style={{ background: "var(--surface-1)", borderBottom: "1px solid var(--border)" }}>
        <span className="font-bold gradient-text">The Vault</span>
        <div className="flex items-center gap-1">
          {navItems.map(item => (
            <Link key={item.href} href={item.href}
              className="p-2 rounded-lg"
              style={{ color: pathname.startsWith(item.href) ? "#818cf8" : "var(--text-muted)" }}>
              {item.icon}
            </Link>
          ))}
        </div>
      </div>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto md:pt-0 pt-14 relative">
        {children}

        {/* Mobile scanner FAB — bottom-right, thumb-reachable. Hidden on chat to avoid overlapping send button */}
        {!pathname.startsWith("/chat") && (
          <button
          id="mobile-scan-fab"
          onClick={openScanner}
          className="md:hidden fixed bottom-6 right-6 z-40 w-14 h-14 rounded-full flex items-center justify-center shadow-2xl btn-press"
          style={{
            background: "var(--accent)",
            boxShadow: "0 8px 0 #8a000e, 0 16px 40px rgba(194,1,20,0.4)",
          }}
          title="Scan document"
          aria-label="Scan document">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
            <circle cx="12" cy="13" r="4" />
          </svg>
        </button>
        )}
      </main>

      <ToastContainer />

      {/* Hidden camera input */}
      <input
        ref={scanInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={async e => {
          const f = e.target.files?.[0];
          if (f) {
            const compressed = await compressImage(f);
            addScanPage(compressed);
          }
          e.target.value = "";
        }}
      />

      {/* Scanner panel */}
      {scannerOpen && (
        <div className="fixed inset-0 z-50 flex flex-col" style={{ background: "var(--surface-0)" }}>
          <div className="flex items-center justify-between px-4 py-4" style={{ borderBottom: "1px solid var(--border)" }}>
            <h2 className="font-bold text-lg">Scan Document</h2>
            <button onClick={() => setScannerOpen(false)} style={{ color: "var(--text-muted)" }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4">
            {scanPages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center gap-4 pb-32">
                <div className="w-20 h-20 rounded-2xl flex items-center justify-center"
                  style={{ background: "rgba(194,1,20,0.1)", border: "2px dashed rgba(194,1,20,0.3)" }}>
                  <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                    <circle cx="12" cy="13" r="4" />
                  </svg>
                </div>
                <p className="font-semibold">Tap the button to scan your first page</p>
                <p className="text-sm" style={{ color: "var(--text-muted)", maxWidth: 280 }}>
                  You can scan multiple pages before uploading — they'll be combined into one document.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {scanPages.map((page, i) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-3 rounded-xl"
                    style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}>
                    <div className="w-10 h-10 rounded-lg overflow-hidden flex-shrink-0 bg-[var(--surface-2)]">
                      <img src={URL.createObjectURL(page)} alt={`Page ${i + 1}`} className="w-full h-full object-cover" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium">Page {i + 1}</p>
                      <p className="text-xs" style={{ color: "var(--text-muted)" }}>{(page.size / 1024).toFixed(0)} KB</p>
                    </div>
                    <button onClick={() => setScanPages(prev => prev.filter((_, j) => j !== i))}
                      style={{ color: "var(--text-muted)" }}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Scanner actions */}
          <div className="px-4 py-4 space-y-3" style={{ borderTop: "1px solid var(--border)" }}>
            {!isOnline && (
              <div className="px-3 py-2 rounded-lg text-xs text-center"
                style={{ background: "rgba(234,179,8,0.1)", border: "1px solid rgba(234,179,8,0.3)", color: "#facc15" }}>
                You're offline — scan will be queued and uploaded when reconnected
              </div>
            )}
            <button
              onClick={() => scanInputRef.current?.click()}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-medium transition-all active:scale-[0.98]"
              style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text-primary)" }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                <circle cx="12" cy="13" r="4" />
              </svg>
              {scanPages.length === 0 ? "Scan first page" : "Scan another page"}
            </button>
            {scanPages.length > 0 && (
              <button
                onClick={finalizeScan}
                className="btn-primary w-full py-3 flex items-center justify-center gap-2">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                {isOnline
                  ? `Upload ${scanPages.length} page${scanPages.length > 1 ? "s" : ""} to Vault`
                  : `Queue ${scanPages.length} page${scanPages.length > 1 ? "s" : ""} for upload`}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Global confirm upload modal */}
      <ConfirmUploadModal
        isOpen={modalOpen}
        status={ingest.status}
        progress={ingest.progress}
        document={ingest.document}
        error={ingest.error}
        duplicateWarning={ingest.duplicateWarning}
        onConfirm={ingest.confirmUpload}
        onAutoConfirm={ingest.triggerAutoConfirm}
        onCancel={() => {
          setModalOpen(false);
          ingest.reset();
        }}
      />
    </div>
  );
}

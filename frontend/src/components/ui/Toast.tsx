"use client";
import { useState, useCallback, useEffect, useRef } from "react";
import { createPortal } from "react-dom";

type ToastVariant = "success" | "error" | "info";

interface ToastItem {
  id: number;
  message: string;
  variant: ToastVariant;
  exiting?: boolean;
}

// Singleton event bus — avoids prop drilling and context providers
const listeners = new Set<(toast: Omit<ToastItem, "id">) => void>();

function emit(toast: Omit<ToastItem, "id">) {
  listeners.forEach(fn => fn(toast));
}

/** Imperative toast API — call from anywhere without hooks */
export const toast = {
  success: (message: string) => emit({ message, variant: "success" }),
  error:   (message: string) => emit({ message, variant: "error" }),
  info:    (message: string) => emit({ message, variant: "info" }),
};

const ICONS: Record<ToastVariant, string> = {
  success: "✓",
  error:   "✕",
  info:    "ℹ",
};

const AUTO_DISMISS_MS = 3000;

/** Render this once in the app shell — it hosts all toasts via a portal. */
export function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(0);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const addToast = useCallback((t: Omit<ToastItem, "id">) => {
    const id = ++nextId.current;
    setToasts(prev => [...prev, { ...t, id }]);

    // Auto-dismiss after timeout
    setTimeout(() => {
      setToasts(prev => prev.map(x => x.id === id ? { ...x, exiting: true } : x));
      // Remove from DOM after animation completes
      setTimeout(() => {
        setToasts(prev => prev.filter(x => x.id !== id));
      }, 300);
    }, AUTO_DISMISS_MS);
  }, []);

  useEffect(() => {
    listeners.add(addToast);
    return () => { listeners.delete(addToast); };
  }, [addToast]);

  if (!mounted) return null;

  return createPortal(
    <div className="toast-container" aria-live="polite" aria-atomic="false">
      {toasts.map(t => (
        <div
          key={t.id}
          className={`toast toast-${t.variant}`}
          style={t.exiting ? { opacity: 0, transform: "translateY(8px)", transition: "opacity 300ms, transform 300ms" } : undefined}
          role="alert"
        >
          <span style={{ fontWeight: 700, fontSize: "1rem", flexShrink: 0 }}>
            {ICONS[t.variant]}
          </span>
          {t.message}
        </div>
      ))}
    </div>,
    document.body
  );
}

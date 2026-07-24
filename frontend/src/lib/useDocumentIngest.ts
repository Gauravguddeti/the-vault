import { useState, useCallback, useRef } from "react";
import { uploadDocument, getDocument, confirmDocument } from "./api";

export type IngestStatus = "idle" | "uploading" | "analyzing" | "awaiting_confirmation" | "confirming" | "ready" | "error";

export function useDocumentIngest(token: string) {
  const [status, setStatus] = useState<IngestStatus>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [document, setDocument] = useState<any>(null);
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null);
  const autoConfirmRef = useRef(false);

  const startIngest = useCallback(async (file: File) => {
    setStatus("uploading");
    setProgress(0);
    setError(null);
    setDocument(null);
    autoConfirmRef.current = false;

    try {
      // 1. Upload with require_confirmation=true
      const uploadRes = await uploadDocument(file, token, true, (p) => setProgress(p)) as any;
      const docId = uploadRes.id;
      
      setStatus("analyzing");

      // 2. Poll until status is awaiting_confirmation or error
      const pollInterval = setInterval(async () => {
        try {
          const doc = await getDocument(docId, token) as any;
          if (doc.status === "awaiting_confirmation") {
            clearInterval(pollInterval);
            setDocument(doc);
            
            if (autoConfirmRef.current) {
              // User clicked Do It Yourself during analysis — auto-confirm now with extracted fields
              confirmUpload({
                title: doc.original_name || "",
                category: doc.category || "",
                date: doc.txn_date || "",
                vendor: doc.vendor || "",
                amount: doc.amount ? parseFloat(doc.amount) : null,
              }, doc.id);
            } else {
              setStatus("awaiting_confirmation");
            }
          } else if (doc.status === "failed") {
            clearInterval(pollInterval);
            setError(doc.error_message || "Analysis failed");
            setStatus("error");
          } else if (doc.status === "ready") {
            // Unlikely to happen if require_confirmation is true, but just in case
            clearInterval(pollInterval);
            setDocument(doc);
            setStatus("ready");
          }
        } catch (e: any) {
          clearInterval(pollInterval);
          setError(e.message || "Failed to check status");
          setStatus("error");
        }
      }, 2000);

    } catch (e: any) {
      setError(e.message || "Upload failed");
      setStatus("error");
    }
  }, [token]);

  const confirmUpload = useCallback(async (fields: any, explicitDocId?: string) => {
    const targetId = explicitDocId || document?.id;
    if (!targetId) return;
    setStatus("confirming");
    setError(null);

    try {
      const res = await confirmDocument(targetId, fields, token) as any;
      if (res.duplicate_warning) setDuplicateWarning(res.duplicate_warning);
      
      // Poll until ready
      const pollInterval = setInterval(async () => {
        try {
          const doc = await getDocument(targetId, token) as any;
          if (doc.status === "ready") {
            clearInterval(pollInterval);
            setDocument(doc);
            setStatus("ready");
          } else if (doc.status === "failed") {
            clearInterval(pollInterval);
            setError(doc.error_message || "Final processing failed");
            setStatus("error");
          }
        } catch (e: any) {
          clearInterval(pollInterval);
          setError(e.message || "Failed to check status");
          setStatus("error");
        }
      }, 2000);

    } catch (e: any) {
      setError(e.message || "Confirmation failed");
      setStatus("error");
    }
  }, [document, token]);

  const reset = useCallback(() => {
    setStatus("idle");
    setProgress(0);
    setError(null);
    setDocument(null);
    setDuplicateWarning(null);
    autoConfirmRef.current = false;
  }, []);

  const triggerAutoConfirm = useCallback(() => {
    autoConfirmRef.current = true;
    if (status === "awaiting_confirmation" && document) {
      confirmUpload({
        title: document.original_name || "",
        category: document.category || "",
        date: document.txn_date || "",
        vendor: document.vendor || "",
        amount: document.amount ? parseFloat(document.amount) : null,
      }, document.id);
    }
  }, [status, document, confirmUpload]);

  return {
    status,
    progress,
    error,
    document,
    duplicateWarning,
    startIngest,
    confirmUpload,
    triggerAutoConfirm,
    reset,
  };
}

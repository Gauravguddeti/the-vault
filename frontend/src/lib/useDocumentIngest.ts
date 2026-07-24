import { useState, useCallback } from "react";
import { uploadDocument, getDocument, confirmDocument } from "./api";

export type IngestStatus = "idle" | "uploading" | "analyzing" | "awaiting_confirmation" | "confirming" | "ready" | "error";

export function useDocumentIngest(token: string) {
  const [status, setStatus] = useState<IngestStatus>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [document, setDocument] = useState<any>(null);
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null);

  const startIngest = useCallback(async (file: File) => {
    setStatus("uploading");
    setProgress(0);
    setError(null);
    setDocument(null);

    try {
      // 1. Upload with require_confirmation=true
      const uploadRes = await uploadDocument(file, token, true, (p) => setProgress(p));
      const docId = uploadRes.id;
      
      setStatus("analyzing");

      // 2. Poll until status is awaiting_confirmation or error
      const pollInterval = setInterval(async () => {
        try {
          const doc = await getDocument(docId, token) as any;
          if (doc.status === "awaiting_confirmation") {
            clearInterval(pollInterval);
            setDocument(doc);
            setStatus("awaiting_confirmation");
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

  const confirmUpload = useCallback(async (fields: any) => {
    if (!document?.id) return;
    setStatus("confirming");
    setError(null);

    try {
      const res = await confirmDocument(document.id, fields, token);
      if (res.duplicate_warning) setDuplicateWarning(res.duplicate_warning);
      
      // Poll until ready
      const pollInterval = setInterval(async () => {
        try {
          const doc = await getDocument(document.id, token) as any;
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
  }, []);

  return {
    status,
    progress,
    error,
    document,
    duplicateWarning,
    startIngest,
    confirmUpload,
    reset,
  };
}

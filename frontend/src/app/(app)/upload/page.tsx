"use client";
import { useState, useCallback, useRef } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
const ALLOWED = ["application/pdf", "image/jpeg", "image/png", "image/tiff", "image/webp"];
const MAX_MB = 25;

export default function UploadPage() {
  const { data: session } = useSession();
  const router = useRouter();
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<"idle" | "uploading" | "done" | "error">("idle");
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const token = (session as any)?.accessToken || "";

  function validateFile(f: File): string | null {
    if (!ALLOWED.includes(f.type)) return `Unsupported type: ${f.type}. Allowed: PDF, JPG, PNG, TIFF, WEBP`;
    if (f.size > MAX_MB * 1024 * 1024) return `File too large (max ${MAX_MB} MB)`;
    return null;
  }

  function pickFile(f: File) {
    const err = validateFile(f);
    if (err) { setError(err); return; }
    setError(""); setFile(f); setStatus("idle");
  }

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) pickFile(f);
  }, []);

  async function handleUpload() {
    if (!file) return;
    setStatus("uploading"); setProgress(0); setError("");

    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);
    xhr.open("POST", `${BACKEND}/api/documents/upload`);
    xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = e => { if (e.lengthComputable) setProgress(Math.round((e.loaded / e.total) * 100)); };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        setStatus("done"); setProgress(100);
        setTimeout(() => router.push("/dashboard"), 1500);
      } else {
        setStatus("error");
        try { setError(JSON.parse(xhr.responseText).detail || "Upload failed"); } catch { setError("Upload failed"); }
      }
    };
    xhr.onerror = () => { setStatus("error"); setError("Network error"); };
    xhr.send(formData);
  }

  return (
    <div className="px-6 py-8 max-w-2xl mx-auto animate-fade-in">
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Upload Document</h1>
        <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>PDF, JPG, PNG, TIFF, WEBP · max 25 MB</p>
      </div>

      {/* Drop zone */}
      <div
        className={`relative rounded-2xl transition-all duration-200 cursor-pointer ${dragging ? "scale-[1.01]" : ""}`}
        style={{
          background: dragging ? "rgba(99,102,241,0.1)" : "var(--surface-1)",
          border: `2px dashed ${dragging || file ? "#6366f1" : "var(--border)"}`,
          padding: "3rem 2rem",
        }}
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}>
        <input ref={inputRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.tiff,.tif,.webp" className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) pickFile(f); }} />

        <div className="text-center">
          {file ? (
            <>
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-4"
                style={{ background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.3)" }}>
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#818cf8" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
                </svg>
              </div>
              <p className="font-semibold text-lg" style={{ color: "var(--text-primary)" }}>{file.name}</p>
              <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                {(file.size / 1024 / 1024).toFixed(2)} MB · {file.type}
              </p>
              <p className="text-xs mt-2" style={{ color: "var(--accent-light)" }}>Click to change file</p>
            </>
          ) : (
            <>
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-4"
                style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
              </div>
              <p className="font-semibold text-lg">Drop your file here</p>
              <p className="text-sm mt-2" style={{ color: "var(--text-muted)" }}>or <span style={{ color: "var(--accent-light)" }}>browse to upload</span></p>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="mt-4 p-3 rounded-xl text-sm" style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", color: "#f87171" }}>
          {error}
        </div>
      )}

      {/* Progress bar */}
      {status === "uploading" && (
        <div className="mt-6">
          <div className="flex justify-between text-sm mb-2" style={{ color: "var(--text-secondary)" }}>
            <span>Uploading…</span><span>{progress}%</span>
          </div>
          <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--surface-3)" }}>
            <div className="h-full rounded-full transition-all duration-300"
              style={{ width: `${progress}%`, background: "linear-gradient(90deg, #4f46e5, #7c3aed)" }} />
          </div>
        </div>
      )}

      {status === "done" && (
        <div className="mt-4 p-3 rounded-xl text-sm text-center" style={{ background: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.3)", color: "#4ade80" }}>
          Upload complete! Processing started — redirecting to dashboard…
        </div>
      )}

      {/* Upload button */}
      {file && status !== "uploading" && status !== "done" && (
        <button id="upload-submit-btn" onClick={handleUpload} className="btn-primary w-full mt-6">
          Upload to Vault
        </button>
      )}
    </div>
  );
}

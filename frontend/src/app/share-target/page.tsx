"use client";
import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useDocumentIngest } from "@/lib/useDocumentIngest";
import ConfirmUploadModal from "@/components/ConfirmUploadModal";

/**
 * Web Share Target API receiver.
 * The OS invokes this page via POST (multipart) when user shares a file into The Vault.
 * Next.js doesn't handle POST on page routes natively, so we read from the URL's
 * share_target form data using a service worker workaround:
 * The manifest's share_target posts to /share-target and the service worker
 * intercepts it and re-issues as a GET with the file in sessionStorage/cache.
 *
 * Simpler PWA-compatible approach: use GET method with a data URL,
 * but files REQUIRE POST. We use the "share target request caching" pattern:
 * the SW caches the file under a key, and this page reads from that cache.
 *
 * For now: manifest uses POST, SW will relay, this page reads from sw-cache.
 * If no SW is available, we degrade gracefully by showing the upload UI.
 */
export default function ShareTargetPage() {
  const { data: session } = useSession();
  const token = (session as any)?.accessToken || "";
  const router = useRouter();
  const ingest = useDocumentIngest(token);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Try to receive the shared file from the service worker cache
    const receiveSharedFile = async () => {
      if (!("caches" in window)) {
        setError("File sharing is only available when installed as a PWA.");
        return;
      }

      try {
        const cache = await caches.open("share-target-cache");
        const keys = await cache.keys();
        if (keys.length === 0) {
          setError("No shared file found. Please try sharing again.");
          return;
        }

        const response = await cache.match(keys[0]);
        if (!response) {
          setError("Could not read shared file.");
          return;
        }

        const blob = await response.blob();
        const filename = keys[0].url.split("/").pop() || "shared-file";
        const sharedFile = new File([blob], decodeURIComponent(filename), { type: blob.type });

        // Clean up cache
        await cache.delete(keys[0]);

        setFile(sharedFile);
        ingest.startIngest(sharedFile);
      } catch (e: any) {
        setError(e.message || "Failed to read shared file.");
      }
    };

    if (token) receiveSharedFile();
  }, [token]);

  if (!session) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-[var(--text-muted)]">Please sign in to use The Vault.</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6" style={{ background: "var(--surface-0)" }}>
      <div className="w-full max-w-md">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: "var(--accent)", boxShadow: "0 4px 0 #8a000e" }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
          </div>
          <span className="font-bold text-xl gradient-text">The Vault</span>
        </div>

        {error ? (
          <div className="p-6 rounded-2xl text-center" style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}>
            <p className="text-red-400 mb-4">{error}</p>
            <button onClick={() => router.push("/upload")} className="btn-primary">
              Go to Upload page
            </button>
          </div>
        ) : (
          <ConfirmUploadModal
            isOpen={true}
            status={ingest.status}
            progress={ingest.progress}
            document={ingest.document}
            error={ingest.error}
            onConfirm={ingest.confirmUpload}
            onAutoConfirm={ingest.triggerAutoConfirm}
            onDismiss={() => router.push("/dashboard")}
            onCancel={() => router.push("/dashboard")}
          />
        )}

        {ingest.status === "ready" && (
          <div className="mt-4 text-center">
            <button onClick={() => router.push("/chat")} className="btn-primary">
              Ask about this document
            </button>
            <button onClick={() => router.push("/dashboard")} className="ml-3 text-sm text-[var(--text-muted)] hover:text-white transition-colors">
              Go to Dashboard
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

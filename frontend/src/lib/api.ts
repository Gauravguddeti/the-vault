/**
 * Typed API client for communicating with the FastAPI backend.
 * Automatically attaches the NextAuth JWT as a Bearer token.
 */
import { getSession } from "next-auth/react";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

async function getAuthHeader(): Promise<Record<string, string>> {
  const session = await getSession();
  // NextAuth v5 JWT is available via session token cookie
  // We pass it via cookie automatically for same-origin, but for cross-origin to FastAPI
  // we use the session's JWT (accessed server-side via auth())
  return {};
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BACKEND}${path}`;
  const res = await fetch(url, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || err.error || "Request failed");
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Documents ──────────────────────────────────────────────────────────

export async function getDocuments(token: string) {
  return apiFetch("/api/documents", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function getDocument(id: string, token: string) {
  return apiFetch(`/api/documents/${id}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function uploadDocument(file: File, token: string, onProgress?: (p: number) => void) {
  return new Promise<any>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);
    xhr.open("POST", `${BACKEND}/api/documents/upload`);
    xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    if (onProgress) xhr.upload.onprogress = e => { if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100)); };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
      else { try { reject(new Error(JSON.parse(xhr.responseText).detail)); } catch { reject(new Error("Upload failed")); } }
    };
    xhr.onerror = () => reject(new Error("Network error"));
    xhr.send(formData);
  });
}

export async function deleteDocument(id: string, token: string) {
  return apiFetch(`/api/documents/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function renameDocument(id: string, name: string, token: string) {
  return apiFetch(`/api/documents/${id}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ original_name: name }),
  });
}

// ── Conversations ──────────────────────────────────────────────────────

export async function getSessions(token: string) {
  return apiFetch("/api/conversations", { headers: { Authorization: `Bearer ${token}` } });
}

export async function createSession(token: string) {
  return apiFetch("/api/conversations", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function getMessages(sessionId: string, token: string) {
  return apiFetch(`/api/conversations/${sessionId}/messages`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function deleteSession(sessionId: string, token: string) {
  return apiFetch(`/api/conversations/${sessionId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
}

// ── Query ──────────────────────────────────────────────────────────────

export async function runQuery(question: string, sessionId: string, token: string) {
  return apiFetch("/api/query", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ question, session_id: sessionId }),
  });
}

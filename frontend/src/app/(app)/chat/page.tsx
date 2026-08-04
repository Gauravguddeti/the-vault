"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import { useSession } from "next-auth/react";
import { useDocumentIngest } from "@/lib/useDocumentIngest";
import ConfirmUploadModal from "@/components/ConfirmUploadModal";
import { compressImage } from "@/lib/imageUtils";
import { SkeletonChatRow } from "@/components/ui/Skeleton";
import { toast } from "@/components/ui/Toast";
import useSWR from "swr";
import { swrFetch } from "@/lib/swrConfig";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

type Session = { id: string; title: string; message_count: number; updated_at: string };
type Message = {
  id: string;
  role: string;
  content: string;
  sources?: any[];
  query_type?: string;
  thinking?: string;
  is_general_knowledge?: boolean;
  created_at: string;
  attachmentName?: string;
};

const ALLOWED_TYPES = ["application/pdf", "image/jpeg", "image/png", "image/tiff", "image/webp", "image/gif"];
const MAX_MB = 25;

/** Collapsible reasoning block shown below assistant messages. */
function ThinkingBlock({ thinking }: { thinking: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-1">
      <button
        onClick={() => setOpen(o => !o)}
        className="text-xs flex items-center gap-1 transition-colors select-none"
        style={{ color: "var(--text-muted)" }}
      >
        <svg
          width="10" height="10" viewBox="0 0 10 10" fill="currentColor"
          style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 150ms ease" }}
        >
          <polygon points="2,1 8,5 2,9" />
        </svg>
        {open ? "Hide reasoning" : "Show reasoning"}
      </button>
      {open && (
        <div
          className="mt-1.5 text-xs px-3 py-2.5 rounded-xl leading-relaxed italic"
          style={{
            background: "rgba(255,255,255,0.03)",
            border: "1px solid var(--border)",
            color: "var(--text-muted)",
            whiteSpace: "pre-wrap",
          }}
        >
          {thinking}
        </div>
      )}
    </div>
  );
}

export default function ChatPage() {
  const { data: session } = useSession();
  const token = (session as any)?.accessToken || "";
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [attachedFile, setAttachedFile] = useState<File | null>(null);
  const [chatDragging, setChatDragging] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  // Streaming state
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // SWR for sessions — shows cached list instantly on tab switch
  const { data: sessions = [], isLoading: loadingSessions, mutate: mutateSessions } = useSWR<Session[]>(
    token ? ["/api/conversations", token] : null,
    ([path, tok]: [string, string]) => swrFetch<Session[]>(path, tok),
    { keepPreviousData: true }
  );
  const messagesEnd = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const ingest = useDocumentIngest(token);

  const api = async (path: string, opts: RequestInit = {}) => {
    const res = await fetch(`${BACKEND}${path}`, {
      ...opts,
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        ...(opts.headers || {}),
      },
    });
    if (res.status === 401) {
      import("next-auth/react").then((m) => m.signOut({ callbackUrl: "/login" }));
    }
    return res;
  };

  
  // Handle native back button on mobile
  useEffect(() => {
    const handlePopState = (e: PopStateEvent) => {
      if (e.state?.chatId) {
        setActiveId(e.state.chatId);
      } else {
        setActiveId(null);
      }
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => { messagesEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  // When a document is ready after confirmation, send a notification message into chat
  useEffect(() => {
    if (ingest.status === "ready" && ingest.document) {
      const doc = ingest.document;
      const category = doc.category || "document";
      const date = doc.txn_date ? ` dated ${doc.txn_date}` : "";
      const vendor = doc.vendor ? ` from ${doc.vendor}` : "";
      const notif: Message = {
        id: `vault-notif-${Date.now()}`,
        role: "assistant",
        content: `Added — it's a ${category}${vendor}${date}. It's indexed and ready to query.`,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, notif]);
      setModalOpen(false);
      setAttachedFile(null);
      ingest.reset();
    }
  }, [ingest.status]);

  async function loadMessages(sid: string) {
    setMessages([]);
    const r = await api(`/api/conversations/${sid}/messages`);
    if (r.ok) setMessages(await r.json());
  }

  async function selectSession(sid: string) {
    window.history.pushState({ chatId: sid }, "", "?chat=" + sid);
    setActiveId(sid);
    await loadMessages(sid);
  }

  async function newChat() {
    const r = await api("/api/conversations", { method: "POST" });
    if (r.ok) {
      const s = await r.json();
      // Optimistically prepend to sessions cache
      mutateSessions([s, ...sessions], false);
      window.history.pushState({ chatId: s.id }, "", "?chat=" + s.id);
      setActiveId(s.id);
      setMessages([]);
    }
  }

  async function deleteSession(sid: string, e: React.MouseEvent) {
    e.stopPropagation();
    setDeletingId(sid);
    await api(`/api/conversations/${sid}`, { method: "DELETE" });
    // Remove from cache optimistically
    mutateSessions(sessions.filter(s => s.id !== sid), false);
    setDeletingId(null);
    if (activeId === sid) { 
      setActiveId(null); 
      setMessages([]);
      setStreamingContent(null);
      window.history.replaceState({}, "", window.location.pathname);
    }
    toast.success("Conversation deleted");
  }

  async function sendMessage(e?: React.FormEvent, overrideQ?: string, explicitChatId?: string) {
    e?.preventDefault();
    const q = overrideQ ?? question.trim();
    const targetId = explicitChatId ?? activeId;
    if (!q || !targetId || loading) return;
    setQuestion("");

    const tempUser: Message = {
      id: "temp-user-" + Date.now(),
      role: "user",
      content: q,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, tempUser]);
    setLoading(true);
    setStreamingContent(""); // start streaming bubble

    // Cancel any in-flight stream
    abortRef.current?.abort();
    const abort = new AbortController();
    abortRef.current = abort;

    try {
      const res = await fetch(
        `${BACKEND}/api/query/stream`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ question: q, session_id: targetId }),
          signal: abort.signal,
        }
      );

      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";
      let finalSources: any[] = [];
      let finalQueryType = "lookup";
      let finalThinking = "";
      let finalIsGeneralKnowledge = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.done) {
              finalSources = data.sources || [];
              finalQueryType = data.query_type || "lookup";
              finalThinking = data.thinking || "";
              finalIsGeneralKnowledge = data.is_general_knowledge || false;
            } else if (data.token) {
              accumulated += data.token;
              setStreamingContent(accumulated);
            }
          } catch {}
        }
      }

      // Commit streaming content → real message
      const assistantMsg: Message = {
        id: "ai-" + Date.now(),
        role: "assistant",
        content: accumulated || "Sorry, I couldn't generate a response.",
        sources: finalSources,
        query_type: finalQueryType,
        thinking: finalThinking,
        is_general_knowledge: finalIsGeneralKnowledge,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, assistantMsg]);
      setStreamingContent(null);

      // Revalidate sessions from DB after a short delay so message_count and title are accurate.
      // The backend saves the user message immediately and the assistant message asynchronously,
      // so we wait 2s for the background task to finish before pulling the real count.
      setTimeout(() => mutateSessions(), 2000);

    } catch (err: any) {
      if (err?.name === "AbortError") return; // intentional cancel
      setStreamingContent(null);
      setMessages(prev => [...prev, {
        id: "err-" + Date.now(), role: "assistant",
        content: "Something went wrong. Please try again.",
        created_at: new Date().toISOString(),
      }]);
    }
    setLoading(false);
  }

  function validateFile(f: File): string | null {
    if (!ALLOWED_TYPES.includes(f.type)) return `Unsupported type. Allowed: PDF, JPG, PNG, WEBP, TIFF.`;
    if (f.size > MAX_MB * 1024 * 1024) return `File too large (max ${MAX_MB} MB).`;
    return null;
  }

  async function handleFileSelect(file: File) {
    if (file.type.startsWith("image/")) {
      file = await compressImage(file);
    }
    const err = validateFile(file);
    if (err) {
      setMessages(prev => [...prev, {
        id: "err-file-" + Date.now(), role: "assistant",
        content: `Couldn't attach that file: ${err}`,
        created_at: new Date().toISOString(),
      }]);
      return;
    }
    setAttachedFile(file);
    // Inject preview bubble
    setMessages(prev => [...prev, {
      id: "attach-preview-" + Date.now(),
      role: "user",
      content: `📎 ${file.name}`,
      attachmentName: file.name,
      created_at: new Date().toISOString(),
    }]);
    // Ask if user wants to vault it
    setMessages(prev => [...prev, {
      id: "attach-ask-" + Date.now(),
      role: "assistant",
      content: `Got it — want me to add "${file.name}" to your Vault so you can ask questions about it?`,
      created_at: new Date().toISOString(),
    }]);
  }

  // Paste listener
  const onPaste = useCallback((e: React.ClipboardEvent) => {
    const items = e.clipboardData.items;
    for (let i = 0; i < items.length; i++) {
      if (items[i].kind === "file") {
        const file = items[i].getAsFile();
        if (file) { handleFileSelect(file); break; }
      }
    }
  }, []);

  function startVaultUpload() {
    if (!attachedFile) return;
    setModalOpen(true);
    ingest.reset();
    ingest.startIngest(attachedFile);
  }

  function discardAttachment() {
    setAttachedFile(null);
    ingest.reset();
    setMessages(prev => [...prev, {
      id: "discard-" + Date.now(), role: "assistant",
      content: "No problem, the file won't be saved.",
      created_at: new Date().toISOString(),
    }]);
  }

  // Chat area drag-drop
  const onChatDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setChatDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && activeId) handleFileSelect(file);
  }, [activeId]);

  // Fetch dynamic prompt suggestions from backend (auto-refreshes after doc changes)
  const { data: suggestionsData } = useSWR<{ suggestions: string[] }>(
    token ? ["/api/documents/suggestions", token] : null,
    ([path, tok]: [string, string]) => swrFetch<{ suggestions: string[] }>(path, tok),
    { keepPreviousData: true, revalidateOnFocus: false }
  );

  const dynamicPrompts = suggestionsData?.suggestions ?? [
    "Upload a receipt or bill to get started",
    "Drop a PDF and ask questions about it",
    "Add a document to your Vault",
  ];

  return (
    <div className="flex h-full w-full">
      {/* Sessions sidebar */}
      <div className={`flex flex-col flex-shrink-0 transition-all duration-300 ${sidebarOpen ? 'w-full md:w-64' : 'w-0 overflow-hidden'} ${activeId ? 'hidden md:flex' : 'flex'}`}
        style={{ background: "var(--surface-0)", borderRight: sidebarOpen ? "1px solid var(--border)" : "none" }}>
        <div className="p-3 whitespace-nowrap min-w-[16rem]">
          <button onClick={newChat}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold transition-all"
            style={{ background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.3)", color: "#818cf8" }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "rgba(99,102,241,0.25)"; (e.currentTarget as HTMLElement).style.transform = "translateY(-1px)"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "rgba(99,102,241,0.15)"; (e.currentTarget as HTMLElement).style.transform = "none"; }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            New chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto py-2 px-2 space-y-1 min-w-[16rem]">
          {loadingSessions ? (
            // Skeleton rows while sessions load
            <div className="space-y-1 px-1">
              {[...Array(4)].map((_, i) => <SkeletonChatRow key={i} />)}
            </div>
          ) : sessions.length === 0 ? (
            <p className="text-xs text-center py-6" style={{ color: "var(--text-muted)" }}>No conversations yet</p>
          ) : sessions.map(s => (
            <div key={s.id} onClick={() => selectSession(s.id)}
              className="group flex items-center gap-2 px-3 py-2.5 rounded-xl cursor-pointer transition-all"
              style={{
                background: activeId === s.id ? "rgba(99,102,241,0.15)" : "transparent",
                border: activeId === s.id ? "1px solid rgba(99,102,241,0.25)" : "1px solid transparent",
              }}>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: activeId === s.id ? "#818cf8" : "var(--text-secondary)" }}>
                  {s.title || "New conversation"}
                </p>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>{s.message_count} messages</p>
              </div>
              <button onClick={e => deleteSession(s.id, e)}
                disabled={deletingId === s.id}
                className="opacity-100 md:opacity-0 md:group-hover:opacity-100 p-2 -mr-2 rounded transition-colors" style={{ color: "var(--text-muted)" }}
                onMouseEnter={e => (e.currentTarget as HTMLElement).style.color = "#f87171"}
                onMouseLeave={e => (e.currentTarget as HTMLElement).style.color = "var(--text-muted)"}>
                {deletingId === s.id ? (
                  <div className="w-3 h-3 border-2 border-[var(--text-muted)] border-t-[var(--accent)] rounded-full animate-spin" />
                ) : (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                  </svg>
                )}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Chat area */}
      <div className={`relative flex-col min-w-0 flex-1 ${!activeId ? 'hidden md:flex' : 'flex'}`}
        onDragOver={e => { e.preventDefault(); if (activeId) setChatDragging(true); }}
        onDragLeave={() => setChatDragging(false)}
        onDrop={onChatDrop}>
        
        {/* Desktop Sidebar Toggle Button */}
        <button 
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="hidden md:flex absolute top-4 left-4 z-40 items-center justify-center w-8 h-8 rounded-lg shadow-sm transition-all"
          style={{ background: "var(--surface-1)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}
          title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
        >
          {sidebarOpen ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          )}
        </button>

        {/* Drop overlay */}
        {chatDragging && (
          <div className="absolute inset-0 z-30 flex items-center justify-center pointer-events-none"
            style={{ background: "rgba(99,102,241,0.12)", border: "2px dashed #6366f1" }}>
            <p className="text-indigo-300 font-medium text-lg">Drop to attach to chat</p>
          </div>
        )}

        {!activeId ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center px-6 animate-fade-in">
            <div className="w-20 h-20 rounded-2xl flex items-center justify-center mb-6"
              style={{ background: "rgba(194,1,20,0.15)", border: "1px solid rgba(99,102,241,0.3)" }}>
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#818cf8" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <h2 className="text-xl font-bold mb-2">Ask your documents anything</h2>
            <p style={{ color: "var(--text-muted)", maxWidth: 380 }} className="text-sm mb-6">
              Start a new chat or pick a conversation. Ask about receipts, spending totals, or any document in your Vault.
            </p>
            {/* Example prompt chips */}
            <div className="flex flex-col gap-2 mb-6 w-full max-w-sm">
              {dynamicPrompts.map(prompt => (
                <button
                  key={prompt}
                  onClick={async () => {
                    const r = await api("/api/conversations", { method: "POST" });
                    if (r.ok) {
                      const s = await r.json();
                      mutateSessions([s, ...sessions], false);
                      window.history.pushState({ chatId: s.id }, "", "?chat=" + s.id);
                      setActiveId(s.id);
                      setMessages([]);
                      // Wait for next tick so activeId is technically set in UI, but pass explicit args anyway
                      setTimeout(() => sendMessage(undefined, prompt, s.id), 0);
                    }
                  }}
                  className="text-left text-sm px-4 py-2.5 rounded-xl transition-all btn-press"
                  style={{
                    background: "var(--surface-1)",
                    border: "1px solid var(--border)",
                    color: "var(--text-secondary)",
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = "rgba(99,102,241,0.4)"; (e.currentTarget as HTMLElement).style.color = "#818cf8"; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = "var(--border)"; (e.currentTarget as HTMLElement).style.color = "var(--text-secondary)"; }}
                >
                  <span style={{ color: "var(--text-muted)" }}>Try: </span>{prompt}
                </button>
              ))}
            </div>
            <button onClick={newChat} className="btn-primary">Start new chat</button>
          </div>
        ) : (
          <>
            {/* Mobile Back Button */}
            <div className="md:hidden flex items-center px-4 py-2 border-b border-white/5" style={{ background: "var(--surface-1)" }}>
              <button 
                onClick={() => {
                  setActiveId(null);
                  window.history.replaceState({}, "", window.location.pathname);
                }}
                className="flex items-center gap-1 text-sm font-medium transition-colors"
                style={{ color: "var(--text-secondary)" }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M15 18l-6-6 6-6"/>
                </svg>
                Conversations
              </button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-4 md:px-6 py-6 space-y-6">
              {messages.map((msg, i) => (
                <div key={msg.id + i}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} animate-slide-up`}
                  style={{ animationDelay: `${Math.min(i * 20, 100)}ms`, animationFillMode: "both" }}>
                  {msg.role === "assistant" && (
                    <div className="w-8 h-8 rounded-xl flex-shrink-0 flex items-center justify-center mr-3 mt-1"
                      style={{ background: "var(--accent)", boxShadow: "0 4px 0 #8a000e" }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
                      </svg>
                    </div>
                  )}
                  <div className="max-w-[90%] md:max-w-[75%] flex flex-col gap-2">
                    <div className="rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap"
                      style={
                        msg.role === "user"
                          ? { background: msg.attachmentName ? "rgba(99,102,241,0.2)" : "var(--accent)", color: "white", borderBottomRightRadius: 4 }
                          : { background: "var(--surface-2)", color: "var(--text-primary)", border: "1px solid var(--border)", borderBottomLeftRadius: 4 }
                      }>
                      {msg.content}
                    </div>

                    {/* Vault confirm actions */}
                    {msg.role === "assistant" && attachedFile && msg.id.startsWith("attach-ask-") &&
                      i === messages.length - 1 && (
                        <div className="flex gap-2 ml-1">
                          <button id="chat-vault-confirm-btn"
                            onClick={startVaultUpload}
                            className="text-xs px-3 py-1.5 rounded-lg font-medium btn-press"
                            style={{ background: "rgba(99,102,241,0.2)", border: "1px solid rgba(99,102,241,0.4)", color: "#818cf8" }}>
                            Upload to Vault
                          </button>
                          <button id="chat-vault-discard-btn"
                            onClick={discardAttachment}
                            className="text-xs px-3 py-1.5 rounded-lg font-medium btn-press"
                            style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>
                            Not now
                          </button>
                        </div>
                      )}

                    {/* Thinking block — collapsible "Show reasoning" toggle */}
                    {msg.role === "assistant" && msg.thinking && (
                      <ThinkingBlock thinking={msg.thinking} />
                    )}

                    {/* Source citations with hover detail */}
                    {msg.role === "assistant" && msg.sources && msg.sources.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        {msg.sources.map((s: any, j: number) => (
                          <div key={j} className="relative group/src">
                            {s.url ? (
                              /* Web search source — clickable external link */
                              <a
                                href={s.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-xs px-2.5 py-1 rounded-full inline-flex items-center gap-1 transition-colors"
                                style={{ background: "rgba(59,130,246,0.12)", color: "#60a5fa", border: "1px solid rgba(59,130,246,0.25)" }}
                                title={s.url}
                              >
                                🌐 {s.document_name && s.document_name.length > 20 ? s.document_name.slice(0, 18) + "…" : (s.document_name || "Web")}
                                <svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 3H2a1 1 0 00-1 1v6a1 1 0 001 1h6a1 1 0 001-1V8m-5-1l6-6m0 0h-3m3 0v3"/></svg>
                              </a>
                            ) : (
                              /* Internal document source — hover tooltip */
                              <>
                                <span
                                  className="text-xs px-2.5 py-1 rounded-full cursor-default"
                                  style={{ background: "var(--surface-3)", color: "var(--text-muted)", border: "1px solid var(--border)" }}>
                                  📄 {s.document_name.length > 20 ? s.document_name.slice(0, 18) + "…" : s.document_name}
                                </span>
                                {/* Hover tooltip */}
                                <div className="absolute bottom-full left-0 mb-1.5 hidden group-hover/src:block z-20 animate-scale-in">
                                  <div className="text-xs px-3 py-2 rounded-xl whitespace-nowrap"
                                    style={{ background: "var(--surface-1)", border: "1px solid var(--border)", boxShadow: "0 4px 16px rgba(0,0,0,0.3)", color: "var(--text-secondary)" }}>
                                    <p className="font-medium" style={{ color: "var(--text-primary)" }}>{s.document_name}</p>
                                    <p>Chunk #{s.chunk_index} · {(s.similarity * 100).toFixed(0)}% match</p>
                                  </div>
                                </div>
                              </>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* General knowledge label — shown when answer came from web, not vault */}
                    {msg.role === "assistant" && msg.is_general_knowledge && (
                      <div className="flex items-center gap-1.5 mt-2">
                        <span
                          className="text-xs px-2.5 py-1 rounded-full inline-flex items-center gap-1.5"
                          style={{
                            background: "rgba(59,130,246,0.10)",
                            border: "1px solid rgba(59,130,246,0.25)",
                            color: "#60a5fa",
                          }}
                        >
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>
                            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                          </svg>
                          General knowledge — not from your Vault
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {/* Streaming bubble */}
              {streamingContent !== null && (
                <div className="flex justify-start animate-slide-up">
                  <div className="w-8 h-8 rounded-xl flex-shrink-0 flex items-center justify-center mr-3 mt-1"
                    style={{ background: "var(--accent)", boxShadow: "0 4px 0 #8a000e" }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
                    </svg>
                  </div>
                  <div className="max-w-[90%] md:max-w-[75%]">
                    <div className="rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap"
                      style={{ background: "var(--surface-2)", color: "var(--text-primary)", border: "1px solid var(--border)", borderBottomLeftRadius: 4 }}>
                      {streamingContent || (
                        <div className="dot-pulse flex gap-1 items-center h-5">
                          <span /><span /><span />
                        </div>
                      )}
                      {streamingContent && <span className="streaming-cursor" />}
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEnd} />
            </div>

            {/* Input */}
            <div className="px-3 md:px-6 py-3 md:py-4" style={{ borderTop: "1px solid var(--border)" }}>
              {attachedFile && (
                <div className="mb-3 flex items-center gap-2 px-3 py-2 rounded-xl text-sm"
                  style={{ background: "rgba(99,102,241,0.1)", border: "1px solid rgba(99,102,241,0.25)" }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#818cf8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                  </svg>
                  <span style={{ color: "#818cf8" }} className="flex-1 truncate">{attachedFile.name}</span>
                  <button onClick={discardAttachment} style={{ color: "var(--text-muted)" }}>✕</button>
                </div>
              )}
              <form onSubmit={sendMessage} className="flex gap-3 items-end">
                {/* Attach button */}
                <button type="button" id="chat-attach-btn"
                  onClick={() => fileInputRef.current?.click()}
                  className="flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-colors"
                  style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text-muted)" }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = "#818cf8"; (e.currentTarget as HTMLElement).style.borderColor = "rgba(99,102,241,0.4)"; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = "var(--text-muted)"; (e.currentTarget as HTMLElement).style.borderColor = "var(--border)"; }}
                  title="Attach file">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                  </svg>
                </button>
                <input ref={fileInputRef} type="file" className="hidden"
                  accept=".pdf,.jpg,.jpeg,.png,.tiff,.tif,.webp"
                  onChange={async e => { const f = e.target.files?.[0]; if (f) await handleFileSelect(f); e.target.value = ""; }}
                />
                <textarea
                  ref={textareaRef}
                  id="chat-input"
                  value={question}
                  placeholder="Ask about your documents, or drop a file here…"
                  className="input-field flex-1 resize-none"
                  rows={1}
                  style={{ minHeight: "40px", maxHeight: "160px" }}
                  disabled={loading}
                  onPaste={onPaste}
                  onKeyDown={e => {
                    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
                    // Auto-resize
                    const ta = e.currentTarget;
                    ta.style.height = "auto";
                    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
                  }}
                  onChange={e => {
                    setQuestion(e.target.value);
                    const ta = e.currentTarget;
                    ta.style.height = "auto";
                    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
                  }}
                />
                <button id="send-btn" type="submit" disabled={!question.trim() || loading}
                  className="btn-primary px-4 flex-shrink-0 disabled:opacity-50 disabled:cursor-not-allowed" style={{ height: "40px" }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
                  </svg>
                </button>
              </form>
              <p className="text-xs mt-2 text-center" style={{ color: "var(--text-muted)" }}>
                Answers are grounded in your documents · attach files to add to Vault
              </p>
            </div>
          </>
        )}
      </div>

      {/* Confirm upload modal (triggered from chat) */}
      <ConfirmUploadModal
        isOpen={modalOpen}
        status={ingest.status}
        progress={ingest.progress}
        document={ingest.document}
        error={ingest.error}
        duplicateWarning={ingest.duplicateWarning}
        onConfirm={ingest.confirmUpload}
        onAutoConfirm={ingest.triggerAutoConfirm}
        onDismiss={() => setModalOpen(false)}
        onCancel={() => {
          setModalOpen(false);
          if (ingest.status !== "ready") {
            setAttachedFile(null);
            ingest.reset();
          }
        }}
      />
    </div>
  );
}

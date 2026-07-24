"use client";
import { useEffect, useState, useRef } from "react";
import { useSession } from "next-auth/react";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

type Session = { id: string; title: string; message_count: number; updated_at: string };
type Message = { id: string; role: string; content: string; sources?: any[]; query_type?: string; created_at: string };

export default function ChatPage() {
  const { data: session } = useSession();
  const token = (session as any)?.accessToken || "";

  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const messagesEnd = useRef<HTMLDivElement>(null);

  const api = (path: string, opts: RequestInit = {}) =>
    fetch(`${BACKEND}${path}`, { ...opts, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...(opts.headers || {}) } });

  useEffect(() => { if (session) loadSessions(); }, [session]);
  useEffect(() => { messagesEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  async function loadSessions() {
    setLoadingSessions(true);
    const r = await api("/api/conversations");
    if (r.ok) { const data = await r.json(); setSessions(data); }
    setLoadingSessions(false);
  }

  async function loadMessages(sid: string) {
    setMessages([]);
    const r = await api(`/api/conversations/${sid}/messages`);
    if (r.ok) setMessages(await r.json());
  }

  async function selectSession(sid: string) {
    setActiveId(sid);
    await loadMessages(sid);
  }

  async function newChat() {
    const r = await api("/api/conversations", { method: "POST" });
    if (r.ok) {
      const s = await r.json();
      setSessions(prev => [s, ...prev]);
      setActiveId(s.id); setMessages([]);
    }
  }

  async function deleteSession(sid: string, e: React.MouseEvent) {
    e.stopPropagation();
    await api(`/api/conversations/${sid}`, { method: "DELETE" });
    setSessions(prev => prev.filter(s => s.id !== sid));
    if (activeId === sid) { setActiveId(null); setMessages([]); }
  }

  async function sendMessage(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || !activeId || loading) return;
    const q = question.trim();
    setQuestion("");

    // Optimistic user message
    const tempUser: Message = { id: "temp-user", role: "user", content: q, created_at: new Date().toISOString() };
    setMessages(prev => [...prev, tempUser]);
    setLoading(true);

    try {
      const r = await api("/api/query", { method: "POST", body: JSON.stringify({ question: q, session_id: activeId }) });
      if (r.ok) {
        const data = await r.json();
        const assistantMsg: Message = { id: "temp-ai-" + Date.now(), role: "assistant", content: data.answer, sources: data.sources, query_type: data.query_type, created_at: new Date().toISOString() };
        setMessages(prev => [...prev, assistantMsg]);
        setSessions(prev => prev.map(s => s.id === activeId ? { ...s, message_count: s.message_count + 2, updated_at: new Date().toISOString() } : s));
      } else {
        setMessages(prev => [...prev, { id: "err", role: "assistant", content: "Sorry, something went wrong. Please try again.", created_at: new Date().toISOString() }]);
      }
    } catch {
      setMessages(prev => [...prev, { id: "err2", role: "assistant", content: "Network error. Is the backend running?", created_at: new Date().toISOString() }]);
    }
    setLoading(false);
  }

  return (
    <div className="flex h-full" style={{ height: "calc(100vh - 0px)" }}>
      {/* Sessions sidebar */}
      <div className="w-64 flex-shrink-0 flex flex-col" style={{ borderRight: "1px solid var(--border)", background: "var(--surface-1)" }}>
        <div className="px-4 py-4" style={{ borderBottom: "1px solid var(--border)" }}>
          <button onClick={newChat} className="btn-primary w-full flex items-center justify-center gap-2 text-sm">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            New chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto py-2 px-2 space-y-1">
          {loadingSessions ? (
            <div className="flex justify-center py-8"><div className="spinner" /></div>
          ) : sessions.length === 0 ? (
            <p className="text-xs text-center py-6" style={{ color: "var(--text-muted)" }}>No conversations yet</p>
          ) : sessions.map(s => (
            <div key={s.id} onClick={() => selectSession(s.id)}
              className="group flex items-center gap-2 px-3 py-2.5 rounded-xl cursor-pointer transition-all"
              style={{ background: activeId === s.id ? "rgba(99,102,241,0.15)" : "transparent", border: activeId === s.id ? "1px solid rgba(99,102,241,0.25)" : "1px solid transparent" }}>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: activeId === s.id ? "#818cf8" : "var(--text-secondary)" }}>
                  {s.title || "New conversation"}
                </p>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>{s.message_count} messages</p>
              </div>
              <button onClick={e => deleteSession(s.id, e)}
                className="opacity-0 group-hover:opacity-100 p-1 rounded" style={{ color: "var(--text-muted)" }}
                onMouseEnter={e => (e.currentTarget as HTMLElement).style.color = "#f87171"}
                onMouseLeave={e => (e.currentTarget as HTMLElement).style.color = "var(--text-muted)"}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {!activeId ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center px-6 animate-fade-in">
            <div className="w-20 h-20 rounded-2xl flex items-center justify-center mb-6"
              style={{ background: "rgba(194,1,20,0.15)", border: "1px solid rgba(99,102,241,0.3)" }}>
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#818cf8" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
            </div>
            <h2 className="text-xl font-bold mb-2">Ask your documents anything</h2>
            <p style={{ color: "var(--text-muted)", maxWidth: 380 }} className="text-sm">
              Start a new chat or select a conversation. Ask about specific receipts, spending totals, vendor information, and more.
            </p>
            <button onClick={newChat} className="btn-primary mt-6">Start new chat</button>
          </div>
        ) : (
          <>
            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
              {messages.map((msg, i) => (
                <div key={msg.id + i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} animate-slide-up`}>
                  {msg.role === "assistant" && (
                    <div className="w-8 h-8 rounded-xl flex-shrink-0 flex items-center justify-center mr-3 mt-1"
                      style={{ background: "var(--accent)", boxShadow: "0 4px 0 #8a000e" }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                      </svg>
                    </div>
                  )}
                  <div className="max-w-[75%]">
                    <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap`}
                      style={msg.role === "user"
                        ? { background: "var(--accent)", color: "white", borderBottomRightRadius: 4 }
                        : { background: "var(--surface-2)", color: "var(--text-primary)", border: "1px solid var(--border)", borderBottomLeftRadius: 4 }}>
                      {msg.content}
                    </div>
                    {msg.role === "assistant" && msg.sources && msg.sources.length > 0 && (
                      <details className="mt-2">
                        <summary className="text-xs cursor-pointer" style={{ color: "var(--text-muted)" }}>
                          {msg.sources.length} source{msg.sources.length !== 1 ? "s" : ""}
                        </summary>
                        <div className="mt-2 space-y-1">
                          {msg.sources.map((s: any, j: number) => (
                            <div key={j} className="text-xs px-3 py-2 rounded-lg"
                              style={{ background: "var(--surface-3)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}>
                              📄 {s.document_name} · chunk {s.chunk_index} · {(s.similarity * 100).toFixed(0)}% match
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex justify-start animate-slide-up">
                  <div className="w-8 h-8 rounded-xl flex-shrink-0 flex items-center justify-center mr-3"
                    style={{ background: "var(--accent)" }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                    </svg>
                  </div>
                  <div className="rounded-2xl px-4 py-3" style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderBottomLeftRadius: 4 }}>
                    <div className="dot-pulse flex gap-1 items-center h-5">
                      <span /><span /><span />
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEnd} />
            </div>

            {/* Input */}
            <div className="px-6 py-4" style={{ borderTop: "1px solid var(--border)" }}>
              <form onSubmit={sendMessage} className="flex gap-3">
                <input id="chat-input" value={question} onChange={e => setQuestion(e.target.value)}
                  placeholder="Ask about your documents…" className="input-field flex-1"
                  disabled={loading} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(e as any); } }} />
                <button id="send-btn" type="submit" disabled={!question.trim() || loading}
                  className="btn-primary px-4 flex-shrink-0 disabled:opacity-50 disabled:cursor-not-allowed">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
                  </svg>
                </button>
              </form>
              <p className="text-xs mt-2 text-center" style={{ color: "var(--text-muted)" }}>
                Answers are grounded in your documents only · Zero hallucination policy
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

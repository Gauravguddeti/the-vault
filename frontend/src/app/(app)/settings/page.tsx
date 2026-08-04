"use client";

import { useEffect, useState } from "react";
import { toast } from "@/components/ui/Toast";
import { useSession } from "next-auth/react";

interface MemoryItem {
  id: string;
  content: string;
  category: string;
  created_at: string;
}

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export default function SettingsPage() {
  const { data: session } = useSession();
  const token = (session as any)?.accessToken || "";
  
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [exitingIds, setExitingIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (token) {
      loadMemories();
    }
  }, [token]);

  async function loadMemories() {
    try {
      const res = await fetch(`${BACKEND}/api/memory`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setMemories(await res.json());
      }
    } catch (err) {
      toast.error("Failed to load memory");
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Are you sure you want to delete this memory? It will no longer influence the assistant's behavior.")) return;
    
    // Start exit animation immediately
    setExitingIds(prev => new Set(prev).add(id));
    
    try {
      const res = await fetch(`${BACKEND}/api/memory/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        // Wait for animation (200ms ease-in collapse + 80ms buffer)
        await new Promise(r => setTimeout(r, 280));
        setMemories(prev => prev.filter(m => m.id !== id));
        setExitingIds(prev => { const s = new Set(prev); s.delete(id); return s; });
        toast.success("Memory deleted");
      } else {
        setExitingIds(prev => { const s = new Set(prev); s.delete(id); return s; });
        toast.error("Failed to delete memory");
      }
    } catch (err) {
      setExitingIds(prev => { const s = new Set(prev); s.delete(id); return s; });
      toast.error("An error occurred");
    }
  }

  return (
    <div className="p-8 max-w-4xl mx-auto w-full">
      <h1 className="text-3xl font-bold mb-2">Settings</h1>
      <p className="text-[var(--text-muted)] mb-8">Manage your account preferences and assistant memory.</p>

      <div className="bg-surface border border-border/50 rounded-2xl p-6">
        <h2 className="text-xl font-semibold mb-4">Assistant Memory</h2>
        <p className="text-sm text-[var(--text-muted)] mb-6">
          The Vault naturally learns your preferences and communication patterns to provide more personalized answers over time. 
          It explicitly separates these preferences from factual document retrieval. You have full control over what it remembers.
        </p>

        {loading ? (
          <div className="flex justify-center p-8">
            <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
          </div>
        ) : memories.length === 0 ? (
          <div className="text-center p-8 border border-dashed border-border/50 rounded-xl bg-background/50">
            <p className="text-[var(--text-muted)]">The assistant hasn't learned any specific preferences yet.</p>
            <p className="text-sm text-[var(--text-muted)] mt-2">Chat more to build a personalized profile!</p>
          </div>
        ) : (
          <div className="space-y-3">
            <div>
              {memories.map((m) => (
                <div 
                  key={m.id}
                  className={`flex items-center justify-between p-4 bg-background rounded-xl border border-border/50 group ${exitingIds.has(m.id) ? "animate-collapse-out" : "animate-fade-in"}`}
                >
                  <div>
                    <p className="text-sm font-medium">{m.content}</p>
                    <p className="text-xs text-[var(--text-muted)] mt-1 capitalize">{m.category} • {new Date(m.created_at).toLocaleDateString()}</p>
                  </div>
                  <button 
                    onClick={() => handleDelete(m.id)}
                    disabled={exitingIds.has(m.id)}
                    className="p-2 rounded-lg text-[var(--text-muted)] hover:text-[var(--status-error)] hover:bg-[var(--status-error)]/10 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                    title="Delete Memory"
                  >
                    {exitingIds.has(m.id) ? (
                      <div className="w-5 h-5 border-2 border-[var(--status-error)] border-t-transparent rounded-full animate-spin"></div>
                    ) : (
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    )}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

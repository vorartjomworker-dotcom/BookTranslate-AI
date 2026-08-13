"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { apiFetch, getApiToken, setApiToken } from "../lib/api";

type Actor = { id: string | null; email: string; display_name: string; role: string; development_identity: boolean };
type ReviewItem = {
  review_id: string;
  assigned_user_id: string | null;
  priority: number;
  status: string;
  book_id: string;
  chapter_title: string | null;
  segment_id: string;
  source_text: string;
  translation_id: string;
  version_id: string;
  version_number: number;
  translated_text: string;
  quality_score: number | null;
};
type User = { id: string; email: string; display_name: string; role: string; is_active: boolean };
type Comment = { id: string; body: string; is_resolved: boolean; author_user_id: string | null; created_at: string };

export default function ReviewerInbox() {
  const [token, setToken] = useState("");
  const [actor, setActor] = useState<Actor | null>(null);
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [comment, setComment] = useState("");
  const [editedText, setEditedText] = useState("");
  const [diff, setDiff] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selected = useMemo(() => items.find((item) => item.review_id === selectedId) ?? items[0] ?? null, [items, selectedId]);

  async function load() {
    setMessage(null);
    const meResponse = await apiFetch("/api/auth/me", { cache: "no-store" });
    if (!meResponse.ok) {
      setActor(null);
      setItems([]);
      throw new Error(meResponse.status === 401 ? "Enter a valid API token." : `Auth returned ${meResponse.status}`);
    }
    const me: Actor = await meResponse.json();
    setActor(me);
    const inboxResponse = await apiFetch("/api/reviews/inbox?status=pending", { cache: "no-store" });
    if (!inboxResponse.ok) throw new Error(`Reviewer inbox returned ${inboxResponse.status}`);
    const inbox: ReviewItem[] = await inboxResponse.json();
    setItems(inbox);
    setSelectedId((current) => inbox.some((item) => item.review_id === current) ? current : inbox[0]?.review_id ?? null);
    if (me.role === "admin") {
      const usersResponse = await apiFetch("/api/admin/users", { cache: "no-store" });
      if (usersResponse.ok) setUsers(await usersResponse.json());
    } else {
      setUsers([]);
    }
  }

  async function loadComments(reviewId: string) {
    const response = await apiFetch(`/api/human-reviews/${reviewId}/comments`, { cache: "no-store" });
    setComments(response.ok ? await response.json() : []);
  }

  useEffect(() => {
    setToken(getApiToken());
    void load().catch((error) => setMessage(error instanceof Error ? error.message : "Could not load reviewer inbox"));
  }, []);

  useEffect(() => {
    if (!selected) {
      setComments([]);
      setEditedText("");
      setDiff([]);
      return;
    }
    setEditedText(selected.translated_text);
    void loadComments(selected.review_id);
  }, [selected?.review_id]);

  async function saveToken() {
    setApiToken(token);
    setBusy(true);
    try {
      await load();
      setMessage("API token saved for this browser.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not authenticate");
    } finally {
      setBusy(false);
    }
  }

  async function resolve(action: "approve" | "reject" | "edit") {
    if (!selected) return;
    setBusy(true);
    try {
      const response = await apiFetch(`/api/human-reviews/${selected.review_id}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, edited_text: action === "edit" ? editedText : null, notes: "Resolved in reviewer inbox" }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `Review action failed with ${response.status}`);
      setMessage(`Review ${action} completed.`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not resolve review");
    } finally {
      setBusy(false);
    }
  }

  async function addComment() {
    if (!selected || !comment.trim()) return;
    const response = await apiFetch(`/api/human-reviews/${selected.review_id}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: comment }),
    });
    const payload = await response.json();
    if (!response.ok) {
      setMessage(payload.detail ?? "Could not add comment");
      return;
    }
    setComment("");
    await loadComments(selected.review_id);
  }

  async function comparePrevious() {
    if (!selected || selected.version_number <= 1) return;
    const response = await apiFetch(
      `/api/translations/${selected.translation_id}/versions/diff?left=${selected.version_number - 1}&right=${selected.version_number}`,
      { cache: "no-store" },
    );
    const payload = await response.json();
    if (!response.ok) {
      setMessage(payload.detail ?? "Could not compare versions");
      return;
    }
    setDiff(payload.word_diff ?? []);
  }

  async function assign(userId: string) {
    if (!selected) return;
    const response = await apiFetch(`/api/human-reviews/${selected.review_id}/assign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId || null, priority: selected.priority }),
    });
    if (response.ok) await load();
  }

  return (
    <main className="review-shell">
      <header className="workspace-header">
        <div className="workspace-title-row">
          <Link href="/" className="back-link">← Library</Link>
          <div><p className="eyebrow">Stage 7 · Human governance</p><h1>Reviewer inbox</h1></div>
        </div>
        <div className="review-auth">
          <input type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Bearer API token" />
          <button className="button primary" onClick={() => void saveToken()} disabled={busy}>Use token</button>
        </div>
      </header>

      {actor ? <div className="workspace-message">Signed in as {actor.display_name} · {actor.role}{actor.development_identity ? " · local dev identity" : ""}</div> : null}
      {message ? <div className="workspace-message">{message}</div> : null}

      <section className="review-grid">
        <aside className="panel-flat review-inbox-list">
          <div className="sidebar-heading"><p className="eyebrow">Pending</p><strong>{items.length} reviews</strong></div>
          {items.map((item) => (
            <button key={item.review_id} className={`segment-row ${selected?.review_id === item.review_id ? "active" : ""}`} onClick={() => setSelectedId(item.review_id)}>
              <span className="segment-position">{item.priority}</span>
              <div className="segment-preview"><strong>{item.chapter_title ?? "Chapter"}</strong><span>{item.source_text}</span></div>
              <span className="score-badge neutral">{item.quality_score === null ? "—" : Math.round(item.quality_score)}</span>
            </button>
          ))}
          {items.length === 0 ? <div className="empty-list">No pending reviews.</div> : null}
        </aside>

        <section className="panel-flat review-detail">
          {selected ? (
            <>
              <div className="editor-heading">
                <div><p className="eyebrow">Review · version {selected.version_number}</p><strong>{selected.chapter_title ?? "Chapter"}</strong></div>
                <div className="workspace-actions">
                  {selected.version_number > 1 ? <button className="button ghost" onClick={() => void comparePrevious()}>Compare previous</button> : null}
                  <Link className="button ghost" href={`/books/${selected.book_id}`}>Open book</Link>
                </div>
              </div>
              {actor?.role === "admin" ? (
                <label className="review-assignment">Assign reviewer
                  <select value={selected.assigned_user_id ?? ""} onChange={(event) => void assign(event.target.value)}>
                    <option value="">Unassigned</option>
                    {users.filter((user) => user.is_active && ["reviewer", "admin"].includes(user.role)).map((user) => <option key={user.id} value={user.id}>{user.display_name} · {user.email}</option>)}
                  </select>
                </label>
              ) : null}
              <div className="dual-editor">
                <label className="editor-column"><span>Source</span><textarea readOnly value={selected.source_text} /></label>
                <label className="editor-column"><span>Reviewed translation</span><textarea value={editedText} onChange={(event) => setEditedText(event.target.value)} /></label>
              </div>
              <div className="review-actions">
                <button className="button ghost" onClick={() => void resolve("reject")} disabled={busy}>Reject</button>
                <button className="button ghost" onClick={() => void resolve("edit")} disabled={busy || !editedText.trim()}>Save edit</button>
                <button className="button primary" onClick={() => void resolve("approve")} disabled={busy}>Approve</button>
              </div>
              {diff.length ? <pre className="version-diff">{diff.join("\n")}</pre> : null}
              <div className="review-comments">
                <h3>Comments</h3>
                {comments.map((item) => <div key={item.id} className={`review-comment ${item.is_resolved ? "resolved" : ""}`}><p>{item.body}</p><small>{new Date(item.created_at).toLocaleString()}</small></div>)}
                <div className="comment-composer"><input value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Add review comment" /><button onClick={() => void addComment()}>Add</button></div>
              </div>
            </>
          ) : <div className="empty-state">Select a pending review.</div>}
        </section>
      </section>
    </main>
  );
}

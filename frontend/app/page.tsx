"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch, apiUrl, getApiToken, oidcLoginUrl, setApiToken } from "./lib/api";

type Book = {
  id: string;
  title: string;
  source_language: string;
  target_language: string;
  original_filename: string | null;
  file_format: string | null;
  status: string;
  description: string | null;
};

export default function Home() {
  const [books, setBooks] = useState<Book[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [tokenDraft, setTokenDraft] = useState("");
  const [signedIn, setSignedIn] = useState(false);
  const [oidcEnabled, setOidcEnabled] = useState(false);

  async function loadBooks() {
    setLoading(true);
    try {
      const response = await apiFetch("/api/books", { cache: "no-store" });
      if (!response.ok) throw new Error(response.status === 401 ? "Sign in to load the protected library." : `Backend returned ${response.status}`);
      setBooks(await response.json());
      setMessage(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load books");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setSignedIn(Boolean(getApiToken()));
    void fetch(`${apiUrl}/api/auth/oidc/config`).then(async (response) => {
      if (response.ok) setOidcEnabled(Boolean((await response.json()).enabled));
    }).catch(() => undefined);
    void loadBooks();
  }, []);

  function saveToken() {
    setApiToken(tokenDraft);
    setSignedIn(Boolean(tokenDraft.trim()));
    setTokenDraft("");
    void loadBooks();
  }

  function signOut() {
    setApiToken("");
    setSignedIn(false);
    setBooks([]);
    setMessage("Signed out.");
  }

  async function uploadBook(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const file = data.get("file");
    if (!(file instanceof File) || !file.name) {
      setMessage("Choose a DOCX or EPUB file first.");
      return;
    }
    setUploading(true);
    setMessage(null);
    try {
      const response = await apiFetch("/api/books/upload", { method: "POST", body: data });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `Upload failed with ${response.status}`);
      form.reset();
      await loadBooks();
      window.location.href = `/books/${payload.book_id}`;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <main className="shell library-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">BookTranslate AI</p>
          <h1 className="brand-title">Technical translation workspace</h1>
        </div>
        <div className="topbar-actions">
          <Link className="button ghost" href="/reviews">Reviews</Link>
          {oidcEnabled ? <a className="button ghost" href={oidcLoginUrl()}>SSO sign in</a> : null}
          {signedIn ? <button className="button ghost" onClick={signOut}>Sign out</button> : null}
          <a className="button ghost" href={`${apiUrl}/docs`} target="_blank" rel="noreferrer">API</a>
          <button className="button ghost" onClick={() => void loadBooks()}>Refresh</button>
        </div>
      </header>

      {!signedIn ? (
        <section className="panel" style={{ padding: 18, marginBottom: 18 }}>
          <p className="eyebrow">Authentication</p>
          <div className="field-row">
            <label className="field">
              <span>API token</span>
              <input type="password" value={tokenDraft} onChange={(event) => setTokenDraft(event.target.value)} placeholder="Paste local app token" />
            </label>
            <div style={{ display: "flex", alignItems: "end", gap: 10 }}>
              <button className="button primary" type="button" onClick={saveToken} disabled={!tokenDraft.trim()}>Use token</button>
              {oidcEnabled ? <a className="button ghost" href={oidcLoginUrl()}>Continue with SSO</a> : null}
            </div>
          </div>
        </section>
      ) : null}

      <section className="hero-grid">
        <div className="panel hero-copy">
          <span className="status-pill success">Stage 8</span>
          <h2>Translate, review, audit and export technical books without losing structure.</h2>
          <p className="muted">
            DOCX/EPUB ingestion, multi-model translation, human editing, book QA, figure Vision/OCR, protected exports and collaborative review are connected in one workflow.
          </p>
          <div className="metric-strip">
            <div><strong>{books.length}</strong><span>books</span></div>
            <div><strong>2</strong><span>source formats</span></div>
            <div><strong>4</strong><span>application roles</span></div>
          </div>
        </div>

        <form className="panel upload-panel" onSubmit={uploadBook}>
          <div className="panel-heading">
            <div><p className="eyebrow">New project</p><h3>Import a technical book</h3></div>
          </div>
          <label className="field"><span>DOCX or EPUB</span><input type="file" name="file" accept=".docx,.epub" required /></label>
          <label className="field"><span>Display title (optional)</span><input type="text" name="title" placeholder="Low-Latency C++" /></label>
          <div className="field-row">
            <label className="field"><span>Source</span><input type="text" name="source_language" defaultValue="en" /></label>
            <label className="field"><span>Target</span><input type="text" name="target_language" defaultValue="ru" /></label>
          </div>
          <button className="button primary" disabled={uploading}>{uploading ? "Importing…" : "Import book"}</button>
          {message ? <p className="inline-alert">{message}</p> : null}
        </form>
      </section>

      <section className="library-section">
        <div className="section-heading">
          <div><p className="eyebrow">Library</p><h2>Your translation projects</h2></div>
          <span className="muted">{loading ? "Loading…" : `${books.length} projects`}</span>
        </div>
        <div className="book-grid">
          {!loading && books.length === 0 ? <div className="panel empty-state">Import your first DOCX or EPUB to start the translation workflow.</div> : null}
          {books.map((book) => (
            <Link className="book-card" href={`/books/${book.id}`} key={book.id}>
              <div className="book-card-top">
                <span className="format-badge">{book.file_format?.toUpperCase() ?? "BOOK"}</span>
                <span className={`status-pill ${book.status === "translated" ? "success" : "neutral"}`}>{book.status}</span>
              </div>
              <h3>{book.title}</h3>
              <p className="muted clamp">{book.original_filename ?? book.description ?? "Structured translation project"}</p>
              <div className="book-meta"><span>{book.source_language.toUpperCase()} → {book.target_language.toUpperCase()}</span><span>Open workspace →</span></div>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}

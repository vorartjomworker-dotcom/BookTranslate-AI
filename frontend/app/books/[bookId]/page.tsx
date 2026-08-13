"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { apiFetch, getDownloadUrl } from "../../lib/api";

type Segment = {
  id: string;
  position: number;
  type: string;
  status: string;
  source_text: string;
  translated_text: string | null;
  translation_id: string | null;
  translation_status: string | null;
  final_version_id: string | null;
  quality_score: number | null;
  pending_review_id: string | null;
  metadata: Record<string, unknown>;
};

type Chapter = { id: string; position: number; title: string | null; segments: Segment[] };
type QA = { overall_score: number; translation_coverage: number; average_segment_quality: number; terminology_consistency: number; human_review_coverage: number; low_quality_segments: number; unresolved_reviews: number; terminology_issues: number; estimated_cost_usd: string };
type Workbench = { book: { id: string; title: string; source_language: string; target_language: string; status: string; file_format: string | null }; chapters: Chapter[]; qa: QA | null; open_terminology_issues: number };
type TerminologyIssue = { id: string; segment_id: string | null; source_term: string; expected_target_term: string; translated_text: string | null; issue_type: string; severity: string; status: string };
type FigureRender = { id: string; asset_id: string; target_language: string; status: string; rendered_regions: number; total_regions: number; created_at: string };

function scoreClass(score: number | null) {
  if (score === null) return "neutral";
  if (score >= 90) return "success";
  if (score >= 80) return "good";
  if (score >= 70) return "warning";
  return "danger";
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="qa-card"><span>{label}</span><strong>{value}</strong>{detail ? <small>{detail}</small> : null}</div>;
}

export default function BookWorkspace() {
  const params = useParams<{ bookId: string }>();
  const bookId = params.bookId;
  const [data, setData] = useState<Workbench | null>(null);
  const [issues, setIssues] = useState<TerminologyIssue[]>([]);
  const [renders, setRenders] = useState<FigureRender[]>([]);
  const [chapterId, setChapterId] = useState<string | null>(null);
  const [segmentId, setSegmentId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [filter, setFilter] = useState<"all" | "review" | "low">("all");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    const [workspaceResponse, issuesResponse, rendersResponse] = await Promise.all([
      apiFetch(`/api/books/${bookId}/workbench`, { cache: "no-store" }),
      apiFetch(`/api/books/${bookId}/terminology-issues`, { cache: "no-store" }),
      apiFetch(`/api/books/${bookId}/figure-renders`, { cache: "no-store" }),
    ]);
    if (!workspaceResponse.ok) {
      if (workspaceResponse.status === 401) throw new Error("Authentication required. Sign in from the Library page.");
      throw new Error(`Workbench returned ${workspaceResponse.status}`);
    }
    const workspace: Workbench = await workspaceResponse.json();
    setData(workspace);
    if (issuesResponse.ok) setIssues(await issuesResponse.json());
    if (rendersResponse.ok) setRenders(await rendersResponse.json());
    const firstChapter = workspace.chapters[0];
    const targetChapter = workspace.chapters.find((item) => item.id === chapterId) ?? firstChapter;
    if (targetChapter) {
      setChapterId(targetChapter.id);
      const targetSegment = targetChapter.segments.find((item) => item.id === segmentId) ?? targetChapter.segments[0];
      if (targetSegment) setSegmentId(targetSegment.id);
    }
  }

  useEffect(() => { void load().catch((error) => setMessage(error instanceof Error ? error.message : "Could not load workspace")); }, [bookId]);

  const activeChapter = useMemo(() => data?.chapters.find((item) => item.id === chapterId) ?? data?.chapters[0] ?? null, [data, chapterId]);
  const visibleSegments = useMemo(() => {
    const rows = activeChapter?.segments ?? [];
    if (filter === "review") return rows.filter((item) => item.pending_review_id || item.status === "needs_review");
    if (filter === "low") return rows.filter((item) => item.quality_score !== null && item.quality_score < 80);
    return rows.filter((item) => item.status !== "superseded");
  }, [activeChapter, filter]);
  const selected = useMemo(() => activeChapter?.segments.find((item) => item.id === segmentId) ?? visibleSegments[0] ?? null, [activeChapter, segmentId, visibleSegments]);

  useEffect(() => { setDraft(selected?.translated_text ?? ""); }, [selected?.id, selected?.translated_text]);

  async function saveEdit() {
    if (!selected?.translation_id || !draft.trim()) { setMessage("This segment needs a generated final translation before manual editing."); return; }
    setBusy(true); setMessage(null);
    try {
      const response = await apiFetch(`/api/translations/${selected.translation_id}/editor-version`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: draft, notes: "Edited in translator workbench" }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `Save failed with ${response.status}`);
      setMessage("Human-reviewed version saved and finalized.");
      await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not save edit"); }
    finally { setBusy(false); }
  }

  async function rebuildQA() {
    if (!data) return;
    setBusy(true); setMessage(null);
    try {
      const response = await apiFetch(`/api/books/${bookId}/qa-report`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ target_language: data.book.target_language, low_quality_threshold: 80 }) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `QA failed with ${response.status}`);
      setMessage("Book QA report rebuilt."); await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not rebuild QA"); }
    finally { setBusy(false); }
  }

  async function runVision() {
    setBusy(true); setMessage(null);
    try {
      const response = await apiFetch(`/api/books/${bookId}/vision-jobs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `Vision job failed with ${response.status}`);
      setMessage(`Figure OCR queued as job ${payload.id}. Translate the new figure_text segments before rendering.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not queue figure OCR"); }
    finally { setBusy(false); }
  }

  async function runFigureRender() {
    setBusy(true); setMessage(null);
    try {
      const response = await apiFetch(`/api/books/${bookId}/figure-render-jobs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `Figure render job failed with ${response.status}`);
      setMessage(`Translated figure rendering queued as job ${payload.id}. Completed renders are embedded automatically in translated DOCX/EPUB exports.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not queue translated figure rendering"); }
    finally { setBusy(false); }
  }

  async function downloadRender(renderId: string) {
    setBusy(true); setMessage(null);
    try {
      const response = await apiFetch(`/api/figure-renders/${renderId}/download-ticket`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `Render download failed with ${response.status}`);
      window.location.href = payload.url;
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not prepare rendered figure download"); }
    finally { setBusy(false); }
  }

  async function download(format: "translated.docx" | "translated.epub") {
    setBusy(true); setMessage(null);
    try { window.location.href = await getDownloadUrl(bookId, format); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not prepare download"); }
    finally { setBusy(false); }
  }

  async function setIssueStatus(issueId: string, status: "resolved" | "ignored") {
    const response = await apiFetch(`/api/terminology-issues/${issueId}/status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
    if (response.ok) await load();
  }

  if (!data) return <main className="shell"><div className="panel loading-panel">{message ?? "Loading translation workspace…"}</div></main>;

  const qa = data.qa;
  const allSegments = data.chapters.flatMap((item) => item.segments).filter((item) => item.status !== "superseded");
  const translated = allSegments.filter((item) => item.translated_text).length;
  const figureText = allSegments.filter((item) => item.type === "figure_text").length;
  const translatedFigureText = allSegments.filter((item) => item.type === "figure_text" && item.translated_text).length;
  const total = allSegments.length;
  const latestRender = renders[0] ?? null;

  return (
    <main className="workspace-shell">
      <header className="workspace-header">
        <div className="workspace-title-row">
          <Link href="/" className="back-link">← Library</Link>
          <div><p className="eyebrow">{data.book.source_language.toUpperCase()} → {data.book.target_language.toUpperCase()} · {data.book.file_format?.toUpperCase() ?? "BOOK"}</p><h1>{data.book.title}</h1></div>
        </div>
        <div className="workspace-actions">
          <Link className="button ghost" href="/reviews">Reviewer inbox</Link>
          <button className="button ghost" onClick={() => void runVision()} disabled={busy}>Run figure OCR</button>
          <button className="button ghost" onClick={() => void runFigureRender()} disabled={busy || translatedFigureText === 0}>Render translated figures</button>
          {latestRender ? <button className="button ghost" onClick={() => void downloadRender(latestRender.id)} disabled={busy}>Latest PNG</button> : null}
          <button className="button ghost" onClick={() => void rebuildQA()} disabled={busy}>Rebuild QA</button>
          <button className="button ghost" onClick={() => void download("translated.docx")} disabled={busy}>DOCX</button>
          <button className="button primary" onClick={() => void download("translated.epub")} disabled={busy}>EPUB</button>
        </div>
      </header>

      <section className="qa-dashboard">
        <Metric label="Book quality" value={qa ? `${qa.overall_score.toFixed(1)}%` : "—"} detail={qa ? "weighted score" : "build QA report"} />
        <Metric label="Translation" value={qa ? `${qa.translation_coverage.toFixed(0)}%` : `${translated}/${total}`} detail="coverage" />
        <Metric label="Figure OCR" value={`${translatedFigureText}/${figureText}`} detail="translated OCR regions" />
        <Metric label="Figure renders" value={`${renders.length}`} detail={latestRender ? `${latestRender.rendered_regions}/${latestRender.total_regions} latest regions` : "none generated"} />
        <Metric label="Terminology" value={qa ? `${qa.terminology_consistency.toFixed(1)}%` : "—"} detail={`${data.open_terminology_issues} open issues`} />
        <Metric label="Human review" value={qa ? `${qa.human_review_coverage.toFixed(0)}%` : "—"} detail={`${qa?.unresolved_reviews ?? 0} pending`} />
        <Metric label="AI cost" value={qa ? `$${Number(qa.estimated_cost_usd).toFixed(4)}` : "—"} detail="translation estimate" />
      </section>

      {message ? <div className="workspace-message">{message}</div> : null}

      <section className="workspace-grid">
        <aside className="chapter-sidebar panel-flat">
          <div className="sidebar-heading"><p className="eyebrow">Structure</p><strong>{data.chapters.length} chapters</strong></div>
          <div className="chapter-list">{data.chapters.map((chapter) => (
            <button key={chapter.id} className={`chapter-button ${activeChapter?.id === chapter.id ? "active" : ""}`} onClick={() => { setChapterId(chapter.id); setSegmentId(chapter.segments[0]?.id ?? null); }}>
              <span>{chapter.position + 1}</span><div><strong>{chapter.title ?? `Chapter ${chapter.position + 1}`}</strong><small>{chapter.segments.length} segments</small></div>
            </button>
          ))}</div>
        </aside>

        <section className="segment-panel panel-flat">
          <div className="segment-toolbar"><div><p className="eyebrow">Segments</p><strong>{activeChapter?.title ?? "Chapter"}</strong></div><div className="segmented-control">{(["all", "review", "low"] as const).map((value) => <button key={value} className={filter === value ? "active" : ""} onClick={() => setFilter(value)}>{value}</button>)}</div></div>
          <div className="segment-list">
            {visibleSegments.map((segment) => (
              <button key={segment.id} className={`segment-row ${selected?.id === segment.id ? "active" : ""}`} onClick={() => setSegmentId(segment.id)}>
                <span className="segment-position">{segment.position + 1}</span><div className="segment-preview"><strong>{segment.type}</strong><span>{segment.source_text}</span></div><span className={`score-badge ${scoreClass(segment.quality_score)}`}>{segment.quality_score === null ? "—" : Math.round(segment.quality_score)}</span>{segment.pending_review_id ? <span className="review-dot" title="Pending human review" /> : null}
              </button>
            ))}
            {visibleSegments.length === 0 ? <div className="empty-list">No segments match this filter.</div> : null}
          </div>
        </section>

        <section className="editor-panel panel-flat">
          {selected ? <>
            <div className="editor-heading"><div><p className="eyebrow">Editor · segment {selected.position + 1}</p><div className="editor-statuses"><span className={`status-pill ${selected.status === "translated" ? "success" : "neutral"}`}>{selected.status}</span><span className={`status-pill ${scoreClass(selected.quality_score)}`}>QA {selected.quality_score === null ? "—" : selected.quality_score.toFixed(1)}</span></div></div><button className="button primary" onClick={() => void saveEdit()} disabled={busy || !selected.translation_id || !draft.trim()}>{busy ? "Saving…" : "Save human version"}</button></div>
            <div className="dual-editor"><label className="editor-column"><span>Source · {data.book.source_language.toUpperCase()}</span><textarea readOnly value={selected.source_text} /></label><label className="editor-column"><span>Translation · {data.book.target_language.toUpperCase()}</span><textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="No final translation yet" /></label></div>
            <div className="fidelity-bar"><span>Fidelity metadata</span><code>{Object.keys(selected.metadata ?? {}).filter((key) => ["hyperlinks", "mathml", "omml", "footnote_refs", "footnote_references", "endnote_references", "note_id", "note_type", "asset_id", "vision_extraction_id", "bbox", "kind"].includes(key)).join(" · ") || "none"}</code></div>
          </> : <div className="empty-state">Select a segment to open the editor.</div>}
        </section>
      </section>

      <section className="issues-panel panel-flat">
        <div className="section-heading compact"><div><p className="eyebrow">Terminology audit</p><h2>Open consistency issues</h2></div><span className="status-pill warning">{issues.filter((item) => item.status === "open").length} open</span></div>
        <div className="issue-table">
          {issues.filter((item) => item.status === "open").slice(0, 20).map((issue) => <div className="issue-row" key={issue.id}><div><strong>{issue.source_term}</strong><span>Expected: {issue.expected_target_term}</span></div><p>{issue.translated_text ?? "No translation"}</p><div className="issue-actions"><button onClick={() => void setIssueStatus(issue.id, "resolved")}>Resolve</button><button onClick={() => void setIssueStatus(issue.id, "ignored")}>Ignore</button></div></div>)}
          {issues.filter((item) => item.status === "open").length === 0 ? <div className="empty-list">No open terminology issues.</div> : null}
        </div>
      </section>
    </main>
  );
}

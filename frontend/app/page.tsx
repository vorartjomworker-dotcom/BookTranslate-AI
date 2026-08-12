const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Home() {
  return (
    <main className="container">
      <section className="card">
        <p className="eyebrow">BookTranslate AI</p>
        <h1>AI translation platform skeleton is running.</h1>
        <p>
          Frontend: Next.js · Backend: FastAPI · Database: PostgreSQL · Cache/queue: Redis
        </p>
        <div className="links">
          <a href={`${apiUrl}/docs`} target="_blank" rel="noreferrer">
            Open FastAPI Swagger
          </a>
          <a href={`${apiUrl}/health`} target="_blank" rel="noreferrer">
            Check backend health
          </a>
        </div>
      </section>
    </main>
  );
}

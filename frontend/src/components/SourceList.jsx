function formatScore(score) {
  if (typeof score !== "number") {
    return "n/a";
  }

  return score.toFixed(3);
}

function sourceLocation(source) {
  const parts = [];
  if (source.section_index !== undefined && source.section_index !== null) {
    parts.push(`section ${source.section_index}`);
  }
  if (source.chunk_index !== undefined && source.chunk_index !== null) {
    parts.push(`chunk ${source.chunk_index}`);
  }
  return parts.join(" · ");
}

export default function SourceList({
  sources = [],
  onEvaluate,
  onEvaluateRagas,
  evaluation,
  ragasEvaluation,
  ragasJob,
  evaluating,
  ragasEvaluating,
}) {
  if (!sources.length) {
    return null;
  }

  return (
    <details className="sources-panel">
      <summary>Sources / evidence ({sources.length})</summary>
      <div className="eval-actions">
        <button className="mini-button eval-button" onClick={onEvaluate} disabled={evaluating}>
          {evaluating ? "Evaluating..." : "Quick eval"}
        </button>
        <button
          className="mini-button eval-button"
          onClick={onEvaluateRagas}
          disabled={ragasEvaluating}
        >
          {ragasEvaluating ? "Starting..." : "Run Deep Eval"}
        </button>
      </div>
      {ragasJob && ["queued", "processing"].includes(ragasJob.status) && (
        <div className="eval-result ragas-result">
          <strong>
            {ragasJob.status === "queued"
              ? "Deep Eval queued"
              : "Deep Eval running"}
          </strong>
          <small>Stage: {ragasJob.stage}</small>
          <ul>
            <li>This can take a few minutes because RAGAS uses Gemini to judge the answer.</li>
            <li>You can keep using the chat while the result is being prepared.</li>
          </ul>
        </div>
      )}
      {evaluation && (
        <div className="eval-result">
          <strong>
            RAG eval: {evaluation.overall_label} ({evaluation.overall_score})
          </strong>
          <small>
            retrieval {evaluation.retrieval_coverage} · relevance{" "}
            {evaluation.answer_relevance} · grounding {evaluation.grounding_overlap}
          </small>
          <ul>
            {evaluation.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      )}
      {ragasEvaluation && (
        <div className="eval-result ragas-result">
          <strong>
            {ragasEvaluation.status === "timed_out"
              ? "RAGAS timed out"
              : ragasEvaluation.status === "failed"
                ? "Deep Eval failed"
                : "Deep Eval complete"}
            : {ragasEvaluation.overall_score ?? "n/a"}
          </strong>
          <small>
            {Object.entries(ragasEvaluation.metrics || {})
              .map(([name, value]) => `${name} ${value ?? "n/a"}`)
              .join(" · ")}
          </small>
          <ul>
            {(ragasEvaluation.notes || []).map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="sources-list">
        {sources.map((source) => (
          <article className="source-card" key={`${source.source_number}-${source.document_id}-${source.chunk_index}`}>
            <div className="source-card-header">
              <strong>{source.source_title}</strong>
              <span>score {formatScore(source.score)}</span>
            </div>
            <small>
              {sourceLocation(source)}
              {source.source_type ? ` · ${source.source_type}` : ""}
            </small>
            <p>{source.preview}</p>
          </article>
        ))}
      </div>
    </details>
  );
}

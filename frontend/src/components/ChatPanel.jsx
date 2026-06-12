import { useEffect, useMemo, useState } from "react";
import { Loader2, Search, Send } from "lucide-react";

import {
  createRagasJob,
  evaluateRag,
  getConversation,
  getRagasJob,
  streamChat,
} from "../api.js";
import SourceList from "./SourceList.jsx";

function createTurnId() {
  if (globalThis.crypto?.randomUUID) {
    return crypto.randomUUID();
  }

  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function ChatPanel({
  user,
  selectedDocumentIds,
  selectedConversationId,
  setSelectedConversationId,
  onConversationsChanged,
  onTraceEvent,
  onTraceReset,
}) {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [evaluatingTurnKey, setEvaluatingTurnKey] = useState(null);
  const [ragasEvaluatingTurnKey, setRagasEvaluatingTurnKey] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function loadConversation() {
      if (!selectedConversationId) {
        setTurns([]);
        return;
      }

      try {
        setError("");
        const conversation = await getConversation(selectedConversationId, user);
        if (!cancelled) {
          setTurns(conversation.turns || []);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
        }
      }
    }

    loadConversation();
    return () => {
      cancelled = true;
    };
  }, [selectedConversationId, user]);

  async function submitQuestion(event) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || busy) return;

    setBusy(true);
    setError("");
    setQuestion("");
    onTraceReset();

    const pendingTurn = {
      question: trimmed,
      answer: "",
      selected_tool: null,
      confidence: "pending",
      pending: true,
    };
    setTurns((current) => [...current, pendingTurn]);

    try {
      const finalEvent = await streamChat(
        {
          conversation_id: selectedConversationId,
          question: trimmed,
          document_ids: selectedDocumentIds,
          limit: 5,
        },
        user,
        onTraceEvent
      );

      const result = finalEvent?.details || {};
      if (result.conversation_id) {
        setSelectedConversationId(result.conversation_id);
      }
      setTurns((current) => [
        ...current.filter((turn) => !turn.pending),
        {
          id: createTurnId(),
          question: trimmed,
          answer: result.answer,
          selected_tool: result.selected_tool,
          confidence: result.confidence,
          document_ids: selectedDocumentIds,
          sources: result.sources || [],
        },
      ]);
      await onConversationsChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const scopeText = useMemo(() => {
    if (selectedDocumentIds.length === 0) {
      return "All accessible documents";
    }
    return `${selectedDocumentIds.length} selected document${
      selectedDocumentIds.length === 1 ? "" : "s"
    }`;
  }, [selectedDocumentIds.length]);

  async function evaluateTurn(turn, turnKey) {
    setEvaluatingTurnKey(turnKey);
    setError("");
    try {
      const response = await evaluateRag(
        {
          question: turn.question,
          answer: turn.answer,
          contexts: (turn.sources || []).map((source) => source.preview || ""),
          source_scores: (turn.sources || [])
            .map((source) => source.score)
            .filter((score) => typeof score === "number"),
        },
        user
      );
      setTurns((current) =>
        current.map((item, index) =>
          `${item.created_at || item.id || index}-${item.question}` === turnKey
            ? { ...item, evaluation: response.evaluation }
            : item
        )
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setEvaluatingTurnKey(null);
    }
  }

  async function evaluateTurnWithRagas(turn, turnKey) {
    setRagasEvaluatingTurnKey(turnKey);
    setError("");
    try {
      const response = await createRagasJob(
        {
          question: turn.question,
          answer: turn.answer,
          contexts: (turn.sources || []).map((source) => source.preview || ""),
          source_scores: (turn.sources || [])
            .map((source) => source.score)
            .filter((score) => typeof score === "number"),
        },
        user
      );
      const job = response.job;
      setTurns((current) =>
        current.map((item, index) =>
          `${item.created_at || item.id || index}-${item.question}` === turnKey
            ? { ...item, ragasJob: job, ragasEvaluation: null }
            : item
        )
      );
      pollRagasJob(job.job_id, turnKey);
    } catch (err) {
      setError(err.message);
    } finally {
      setRagasEvaluatingTurnKey(null);
    }
  }

  async function pollRagasJob(jobId, turnKey) {
    const maxAttempts = 100;

    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 3000));

      try {
        const job = await getRagasJob(jobId, user);
        setTurns((current) =>
          current.map((item, index) =>
            `${item.created_at || item.id || index}-${item.question}` === turnKey
              ? {
                  ...item,
                  ragasJob: job,
                  ragasEvaluation:
                    job.status === "completed"
                      ? job.result
                      : job.status === "failed"
                        ? {
                            status: "failed",
                            overall_score: job.fallback_result?.overall_score ?? null,
                            metrics: job.fallback_result
                              ? {
                                  quick_retrieval_coverage:
                                    job.fallback_result.retrieval_coverage,
                                  quick_answer_relevance:
                                    job.fallback_result.answer_relevance,
                                  quick_grounding_overlap:
                                    job.fallback_result.grounding_overlap,
                                }
                              : {},
                            notes: [
                              job.error || "Deep evaluation failed.",
                              "Showing quick evaluation fallback if available.",
                            ],
                          }
                        : item.ragasEvaluation,
                }
              : item
          )
        );

        if (["completed", "failed"].includes(job.status)) {
          return;
        }
      } catch (err) {
        setError(err.message);
        return;
      }
    }

    setTurns((current) =>
      current.map((item, index) =>
        `${item.created_at || item.id || index}-${item.question}` === turnKey
          ? {
              ...item,
              ragasEvaluation: {
                status: "timed_out",
                overall_score: null,
                metrics: {},
                notes: [
                  "Deep Eval is still running longer than expected.",
                  "Try again later or use Quick eval for immediate feedback.",
                ],
              },
            }
          : item
      )
    );
  }

  return (
    <main className="chat-panel">
      <header className="chat-header">
        <div>
          <h1>LegalMind AI</h1>
          <p>{scopeText}</p>
        </div>
        <Search size={22} />
      </header>

      <section className="messages">
        {turns.length === 0 && (
          <div className="empty-chat">
            Ask about clauses, termination periods, obligations, compliance gaps, or compare selected documents.
          </div>
        )}
        {turns.map((turn, index) => {
          const turnKey = `${turn.created_at || turn.id || index}-${turn.question}`;
          return (
          <article className="turn" key={turnKey}>
            <div className="question">{turn.question}</div>
            <div className={turn.pending ? "answer pending" : "answer"}>
              <p>{turn.pending ? "Waiting for the agent..." : turn.answer}</p>
              <div className="answer-meta">
                {turn.selected_tool && <span>{turn.selected_tool}</span>}
                {turn.confidence && <span>{turn.confidence}</span>}
              </div>
              <SourceList
                sources={turn.sources || []}
                evaluation={turn.evaluation}
                ragasEvaluation={turn.ragasEvaluation}
                ragasJob={turn.ragasJob}
                evaluating={evaluatingTurnKey === turnKey}
                ragasEvaluating={ragasEvaluatingTurnKey === turnKey}
                onEvaluate={() => evaluateTurn(turn, turnKey)}
                onEvaluateRagas={() => evaluateTurnWithRagas(turn, turnKey)}
              />
            </div>
          </article>
          );
        })}
        {busy && (
          <div className="thinking">
            <Loader2 className="spin" size={18} />
            Thinking through the selected documents...
          </div>
        )}
      </section>

      {error && <div className="error-banner">{error}</div>}

      <form className="chat-input" onSubmit={submitQuestion}>
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask about termination clauses, obligations, risks..."
        />
        <button className="primary-icon-button" disabled={busy || !question.trim()} title="Send">
          <Send size={18} />
        </button>
      </form>
    </main>
  );
}

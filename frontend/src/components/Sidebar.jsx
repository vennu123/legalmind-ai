import { useState } from "react";
import { FileText, Loader2, MessageSquare, Plus, RefreshCw, Trash2 } from "lucide-react";

import { formatBytes, shortId } from "../utils/format.js";

export default function Sidebar({
  documents,
  processingJobs,
  conversations,
  selectedDocumentIds,
  selectedConversationId,
  onToggleDocument,
  onNewChat,
  onSelectConversation,
  onDeleteConversation,
  onDeleteDocument,
  onRetryJob,
  onDismissJob,
  onRefresh,
  busy,
}) {
  const [visibleDocumentCount, setVisibleDocumentCount] = useState(3);
  const [visibleConversationCount, setVisibleConversationCount] = useState(4);
  const visibleDocuments = documents.slice(0, visibleDocumentCount);
  const visibleConversations = conversations.slice(0, visibleConversationCount);

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h2>Workspace</h2>
        <button className="icon-button" onClick={onRefresh} disabled={busy} title="Refresh">
          <RefreshCw size={18} />
        </button>
      </div>

      <button className="new-chat-button" onClick={onNewChat}>
        <Plus size={18} />
        New Chat
      </button>

      <section className="sidebar-section documents-section">
        <div className="section-title">
          <FileText size={16} />
          Documents
        </div>
        <div className="sidebar-list scroll-list">
          {documents.length === 0 && <p className="empty-text">No documents yet.</p>}
          {visibleDocuments.map((document) => (
            <div className="document-row" key={document.document_id}>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={selectedDocumentIds.includes(document.document_id)}
                  onChange={() => onToggleDocument(document.document_id)}
                />
                <span>
                  <strong>{document.filename}</strong>
                  <small>
                    {formatBytes(document.file_size_bytes)} · {document.chunk_count} chunks
                  </small>
                  <small>{shortId(document.document_id)}</small>
                </span>
              </label>
              <button
                className="icon-button danger"
                onClick={() => onDeleteDocument(document.document_id)}
                title="Delete document"
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
          {documents.length > 3 && (
            <button
              className="list-toggle"
              onClick={() =>
                setVisibleDocumentCount((count) =>
                  count >= documents.length ? 3 : Math.min(count + 3, documents.length)
                )
              }
            >
              {visibleDocumentCount >= documents.length
                ? "Show fewer documents"
                : `Show ${Math.min(3, documents.length - visibleDocumentCount)} more`}
            </button>
          )}
        </div>
      </section>

      <section className="sidebar-section processing-section">
        <div className="section-title">
          <Loader2 size={16} />
          Processing
        </div>
        <div className="sidebar-list scroll-list">
          {processingJobs.length === 0 && <p className="empty-text">No active uploads.</p>}
          {processingJobs.map((job) => {
            const total = job.total_chunks || 0;
            const progress = total
              ? Math.max(((job.stored_chunks || job.embedded_chunks || 0) / total) * 100, 8)
              : 12;

            return (
              <div className={`job-row ${job.status}`} key={job.job_id}>
                <strong>{job.filename}</strong>
                <small>
                  {job.status} · {job.stage}
                </small>
                {total > 0 && (
                  <small>
                    Embedded {job.embedded_chunks || 0} / {total} · Stored{" "}
                    {job.stored_chunks || 0} / {total}
                  </small>
                )}
                <div className="progress-bar compact">
                  <span style={{ width: `${progress}%` }} />
                </div>
                {job.status === "failed" && (
                  <div className="job-actions">
                    <button className="mini-button" onClick={() => onRetryJob(job.job_id)}>
                      Retry
                    </button>
                    <button className="mini-button" onClick={() => onDismissJob(job.job_id)}>
                      Remove
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="sidebar-section conversations-section">
        <div className="section-title">
          <MessageSquare size={16} />
          Conversations
        </div>
        <div className="sidebar-list scroll-list">
          {conversations.length === 0 && <p className="empty-text">No chats yet.</p>}
          {visibleConversations.map((conversation) => (
            <div
              className={
                conversation.conversation_id === selectedConversationId
                  ? "conversation-row active"
                  : "conversation-row"
              }
              key={conversation.conversation_id}
            >
              <button onClick={() => onSelectConversation(conversation.conversation_id)}>
                <strong>{conversation.title}</strong>
                <small>{conversation.turn_count} turns</small>
              </button>
              <button
                className="icon-button danger"
                onClick={() => onDeleteConversation(conversation.conversation_id)}
                title="Delete conversation"
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
          {conversations.length > 4 && (
            <button
              className="list-toggle"
              onClick={() =>
                setVisibleConversationCount((count) =>
                  count >= conversations.length
                    ? 4
                    : Math.min(count + 4, conversations.length)
                )
              }
            >
              {visibleConversationCount >= conversations.length
                ? "Show fewer chats"
                : `Show ${Math.min(4, conversations.length - visibleConversationCount)} more`}
            </button>
          )}
        </div>
      </section>
    </aside>
  );
}

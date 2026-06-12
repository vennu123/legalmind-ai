import { useEffect, useState } from "react";
import { Loader2, LogOut } from "lucide-react";

import {
  deleteConversation,
  deleteDocument,
  deleteJob,
  getConversations,
  getDocuments,
  getJob,
  getJobs,
  retryJob,
} from "./api.js";
import ChatPanel from "./components/ChatPanel.jsx";
import LoginScreen from "./components/LoginScreen.jsx";
import SetupNotice from "./components/SetupNotice.jsx";
import Sidebar from "./components/Sidebar.jsx";
import TracePanel from "./components/TracePanel.jsx";
import UploadBar from "./components/UploadBar.jsx";
import { isFirebaseConfigured, signOutUser, watchAuth } from "./firebase.js";

export default function App() {
  const [user, setUser] = useState(null);
  const [authReady, setAuthReady] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [processingJobs, setProcessingJobs] = useState([]);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([]);
  const [selectedConversationId, setSelectedConversationId] = useState(null);
  const [traceEvents, setTraceEvents] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    return watchAuth((nextUser) => {
      setUser(nextUser);
      setAuthReady(true);
    });
  }, []);

  useEffect(() => {
    refreshWorkspace();
  }, [user]);

  useEffect(() => {
    if (!user || processingJobs.length === 0) return;

    const intervalId = window.setInterval(async () => {
      const activeJobs = processingJobs.filter((job) =>
        ["queued", "processing"].includes(job.status)
      );

      if (activeJobs.length === 0) return;

      const updatedJobs = await Promise.all(
        activeJobs.map((job) => getJob(job.job_id, user).catch(() => job))
      );

      setProcessingJobs((current) =>
        current.map((job) => {
          const updatedJob = updatedJobs.find((item) => item.job_id === job.job_id);
          return updatedJob || job;
        })
      );

      if (updatedJobs.some((job) => job.status === "completed")) {
        await refreshWorkspace();
        window.setTimeout(() => {
          setProcessingJobs((current) =>
            current.filter((job) => job.status !== "completed")
          );
        }, 5000);
      }
    }, 2000);

    return () => window.clearInterval(intervalId);
  }, [user, processingJobs]);

  async function refreshWorkspace() {
    if (!user) return;
    setBusy(true);
    setError("");
    try {
      const [documentResponse, conversationResponse] = await Promise.all([
        getDocuments(user),
        getConversations(user),
      ]);
      const jobResponse = await getJobs(user);
      setDocuments(documentResponse.documents || []);
      setConversations(conversationResponse.conversations || []);
      setProcessingJobs(
        (jobResponse.jobs || []).filter((job) =>
          ["queued", "processing", "failed"].includes(job.status)
        )
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function handleJobStarted(job) {
    setProcessingJobs((current) => {
      if (current.some((item) => item.job_id === job.job_id)) {
        return current;
      }

      return [job, ...current];
    });
  }

  async function handleRetryJob(jobId) {
    const result = await retryJob(jobId, user);
    const retriedJob = result.job;
    setProcessingJobs((current) =>
      current.map((job) => (job.job_id === jobId ? retriedJob : job))
    );
  }

  async function handleDismissJob(jobId) {
    const previousJobs = processingJobs;
    setProcessingJobs((current) => current.filter((job) => job.job_id !== jobId));
    setError("");

    try {
      await deleteJob(jobId, user);
    } catch (err) {
      setProcessingJobs(previousJobs);
      setError(err.message);
    }
  }

  function toggleDocument(documentId) {
    setSelectedDocumentIds((current) =>
      current.includes(documentId)
        ? current.filter((id) => id !== documentId)
        : [...current, documentId]
    );
  }

  async function handleDeleteDocument(documentId) {
    const confirmed = window.confirm("Delete this document and its vector chunks?");
    if (!confirmed) return;
    await deleteDocument(documentId, user);
    setSelectedDocumentIds((current) => current.filter((id) => id !== documentId));
    await refreshWorkspace();
  }

  async function handleDeleteConversation(conversationId) {
    const confirmed = window.confirm("Delete this conversation?");
    if (!confirmed) return;
    await deleteConversation(conversationId, user);
    if (selectedConversationId === conversationId) {
      setSelectedConversationId(null);
    }
    await refreshWorkspace();
  }

  async function handleSignOut() {
    setSelectedConversationId(null);
    setSelectedDocumentIds([]);
    setTraceEvents([]);
    await signOutUser();
  }

  function handleSelectConversation(conversationId) {
    setTraceEvents([]);
    setSelectedConversationId(conversationId);
  }

  if (!isFirebaseConfigured) {
    return <SetupNotice />;
  }

  if (!authReady) {
    return (
      <main className="loading-screen">
        <Loader2 className="spin" size={28} />
      </main>
    );
  }

  if (!user) {
    return <LoginScreen />;
  }

  return (
    <div className="app-shell">
      <Sidebar
        documents={documents}
        processingJobs={processingJobs}
        conversations={conversations}
        selectedDocumentIds={selectedDocumentIds}
        selectedConversationId={selectedConversationId}
        onToggleDocument={toggleDocument}
        onNewChat={() => setSelectedConversationId(null)}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
        onDeleteDocument={handleDeleteDocument}
        onRetryJob={handleRetryJob}
        onDismissJob={handleDismissJob}
        onRefresh={refreshWorkspace}
        busy={busy}
      />

      <section className="main-area">
        <header className="topbar">
          <UploadBar
            user={user}
            onUploaded={refreshWorkspace}
            onJobStarted={handleJobStarted}
          />
          <div className="user-menu">
            <span>{user.displayName || user.email}</span>
            <button className="icon-button" onClick={handleSignOut} title="Sign out">
              <LogOut size={18} />
            </button>
          </div>
        </header>

        {error && <div className="error-banner">{error}</div>}

        <ChatPanel
          user={user}
          selectedDocumentIds={selectedDocumentIds}
          selectedConversationId={selectedConversationId}
          setSelectedConversationId={setSelectedConversationId}
          onConversationsChanged={refreshWorkspace}
          onTraceReset={() => setTraceEvents([])}
          onTraceEvent={(event) => setTraceEvents((current) => [...current, event])}
        />
      </section>

      <TracePanel events={traceEvents} />
    </div>
  );
}

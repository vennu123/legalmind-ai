import { useState } from "react";
import { Loader2, Upload, X } from "lucide-react";

import { uploadDocument } from "../api.js";

export default function UploadBar({ user, onUploaded, onJobStarted }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState(null);

  async function handleUpload() {
    if (!file) return;
    await submitUpload(file, false);
  }

  async function submitUpload(uploadFile, replace) {
    setBusy(true);
    try {
      const result = await uploadDocument(uploadFile, replace, user);
      if (result.status === "already_exists") {
        setDialog({
          type: "info",
          title: "Already Uploaded",
          message: "This exact file is already in your workspace, so no new ingestion job was created.",
        });
        await onUploaded();
      } else {
        onJobStarted({
          job_id: result.job_id,
          filename: result.filename || uploadFile.name,
          status: result.status,
          stage: result.stage,
          total_chunks: 0,
          embedded_chunks: 0,
          stored_chunks: 0,
        });
        setFile(null);
      }
      setFile(null);
    } catch (error) {
      const detail = error.detail;
      if (error.status === 409 && typeof detail === "object") {
        setDialog({
          type: "replace",
          title: "File Already Exists",
          message: detail.message,
          filename: detail.filename,
          existingDocumentId: detail.existing_document_id,
          newDocumentId: detail.new_document_id,
        });
      } else {
        setDialog({
          type: "error",
          title: "Upload Failed",
          message: error.message,
        });
      }
    } finally {
      setBusy(false);
    }
  }

  async function confirmReplace() {
    if (!file) return;
    await submitUpload(file, true);
  }

  function closeDialog() {
    setDialog(null);
  }

  return (
    <section className="upload-bar">
      <label className="file-picker">
        <Upload size={18} />
        <input
          type="file"
          accept=".pdf,.docx,.csv,.json,.txt,.html,.htm,.md"
          onChange={(event) => setFile(event.target.files?.[0] || null)}
        />
        <span>{file ? file.name : "Choose document"}</span>
      </label>
      <button className="secondary-button" onClick={handleUpload} disabled={!file || busy}>
        {busy ? <Loader2 className="spin" size={18} /> : <Upload size={18} />}
        Upload
      </button>
      {dialog && (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-panel" role="dialog" aria-modal="true">
            <header className="modal-header">
              <h2>{dialog.title}</h2>
              <button className="icon-button" onClick={closeDialog} title="Close">
                <X size={18} />
              </button>
            </header>
            <p>{dialog.message}</p>
            {dialog.type === "replace" && (
              <div className="modal-details">
                <span>{dialog.filename}</span>
                <small>Existing: {dialog.existingDocumentId}</small>
                <small>New: {dialog.newDocumentId}</small>
              </div>
            )}
            <footer className="modal-actions">
              <button className="secondary-button" onClick={closeDialog}>
                Close
              </button>
              {dialog.type === "replace" && (
                <button className="primary-button modal-primary" onClick={confirmReplace} disabled={busy}>
                  {busy ? <Loader2 className="spin" size={18} /> : null}
                  Replace File
                </button>
              )}
            </footer>
          </section>
        </div>
      )}
    </section>
  );
}

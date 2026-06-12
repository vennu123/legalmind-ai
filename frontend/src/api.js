const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function getAuthHeaders(user) {
  if (!user) {
    return {};
  }

  const token = await user.getIdToken();
  return {
    Authorization: `Bearer ${token}`,
  };
}

async function readJson(response) {
  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function request(path, options = {}, user = null) {
  const authHeaders = await getAuthHeaders(user);
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...authHeaders,
      ...(options.headers || {}),
    },
  });
  const data = await readJson(response);

  if (!response.ok) {
    const detail = data?.detail || data?.message || response.statusText;
    const error = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    error.status = response.status;
    error.data = data;
    error.detail = detail;
    throw error;
  }

  return data;
}

export function getDocuments(user) {
  return request("/documents", {}, user);
}

export function getConversations(user) {
  return request("/conversations", {}, user);
}

export function getJob(jobId, user) {
  return request(`/jobs/${jobId}`, {}, user);
}

export function getJobs(user) {
  return request("/jobs", {}, user);
}

export function retryJob(jobId, user) {
  return request(`/jobs/${jobId}/retry`, { method: "POST" }, user);
}

export function deleteJob(jobId, user) {
  return request(`/jobs/${jobId}`, { method: "DELETE" }, user);
}

export function uploadDocument(file, replace, user) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("replace", String(replace));

  return request(
    "/documents/upload",
    {
      method: "POST",
      body: formData,
    },
    user
  );
}

export function deleteDocument(documentId, user) {
  return request(`/documents/${documentId}`, { method: "DELETE" }, user);
}

export function askChat(payload, user) {
  return request(
    "/chat",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    user
  );
}

export async function streamChat(payload, user, onEvent) {
  const authHeaders = await getAuthHeaders(user);
  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: {
      ...authHeaders,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const data = await readJson(response);
    const detail = data?.detail || data?.message || response.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalEvent = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";

    for (const block of blocks) {
      const dataLine = block
        .split("\n")
        .find((line) => line.startsWith("data: "));

      if (!dataLine) continue;

      const event = JSON.parse(dataLine.slice(6));
      onEvent(event);

      if (event.type === "done") {
        finalEvent = event;
      }
    }
  }

  return finalEvent;
}

export function getConversation(conversationId, user) {
  return request(`/conversations/${conversationId}`, {}, user);
}

export function deleteConversation(conversationId, user) {
  return request(`/conversations/${conversationId}`, { method: "DELETE" }, user);
}

export function evaluateRag(payload, user) {
  return request(
    "/eval/rag",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    user
  );
}

export function evaluateRagas(payload, user) {
  return request(
    "/eval/ragas",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    user
  );
}

export function createRagasJob(payload, user) {
  return request(
    "/eval/ragas/jobs",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    user
  );
}

export function getRagasJob(jobId, user) {
  return request(`/eval/ragas/jobs/${jobId}`, {}, user);
}

import { Activity, CheckCircle2, CircleAlert, CircleDot, Wrench } from "lucide-react";

function iconForType(type) {
  if (type === "action") return <Wrench size={16} />;
  if (type === "observation") return <CircleDot size={16} />;
  if (type === "final" || type === "done") return <CheckCircle2 size={16} />;
  if (type === "error") return <CircleAlert size={16} />;
  return <Activity size={16} />;
}

export default function TracePanel({ events }) {
  return (
    <aside className="trace-panel">
      <header className="trace-header">
        <h2>Agent Trace</h2>
      </header>

      <div className="trace-list">
        {events.length === 0 && (
          <p className="empty-text">SSE events will appear here while the agent works.</p>
        )}
        {events.map((event, index) => (
          <article className={`trace-event ${event.type}`} key={`${event.type}-${index}`}>
            <div className="trace-icon">{iconForType(event.type)}</div>
            <div className="trace-body">
              <strong>{event.type}</strong>
              <p>{event.message}</p>
              {event.details && Object.keys(event.details).length > 0 && (
                <pre>{JSON.stringify(event.details, null, 2)}</pre>
              )}
            </div>
          </article>
        ))}
      </div>
    </aside>
  );
}

export default function SetupNotice() {
  return (
    <main className="setup-screen">
      <section className="setup-panel">
        <h1>LegalMind AI</h1>
        <p>
          Firebase web config is not set yet. Create a web app in Firebase Project
          Settings, then fill `frontend/.env` from `frontend/.env.example`.
        </p>
        <pre>{`VITE_FIREBASE_API_KEY=...
VITE_FIREBASE_AUTH_DOMAIN=...
VITE_FIREBASE_PROJECT_ID=legalmind-ai-498509
VITE_FIREBASE_APP_ID=...`}</pre>
      </section>
    </main>
  );
}

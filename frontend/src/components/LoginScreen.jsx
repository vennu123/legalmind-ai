import { signInWithGoogle } from "../firebase.js";

export default function LoginScreen() {
  return (
    <main className="login-screen">
      <section className="login-panel">
        <div className="brand-mark">LM</div>
        <h1>LegalMind AI</h1>
        <p>Sign in to upload documents and chat with your legal workspace.</p>
        <button className="primary-button" onClick={signInWithGoogle}>
          Sign In With Google
        </button>
      </section>
    </main>
  );
}

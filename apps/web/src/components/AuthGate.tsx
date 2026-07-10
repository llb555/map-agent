import { FormEvent, ReactNode, useEffect, useState } from "react";
import { getAuthSession, isAuthConfigured, signIn, signUp, subscribeAuth } from "../lib/auth";

export function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState(getAuthSession());
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => subscribeAuth(setSession), []);
  if (!isAuthConfigured()) return <>{children}</>;
  if (session) return <>{children}</>;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      if (mode === "signin") {
        await signIn(email.trim(), password);
      } else {
        const created = await signUp(email.trim(), password);
        if (!created) setMessage("注册成功，请先在邮箱中完成确认。 ");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "认证失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-panel" aria-labelledby="auth-title">
        <div className="auth-brand">
          <span>ARCADE ROUTE INTELLIGENCE</span>
          <strong>Arcadegent</strong>
        </div>
        <div className="auth-copy">
          <span className="auth-index">SECURE WORKSPACE / 01</span>
          <h1 id="auth-title">进入你的机厅决策工作台</h1>
          <p>登录后，会话历史、路线任务和知识库权限将绑定到你的账号。</p>
        </div>
        <form className="auth-form" onSubmit={submit}>
          <div className="auth-tabs" role="tablist" aria-label="认证模式">
            <button type="button" className={mode === "signin" ? "is-active" : ""} onClick={() => setMode("signin")}>登录</button>
            <button type="button" className={mode === "signup" ? "is-active" : ""} onClick={() => setMode("signup")}>注册</button>
          </div>
          <label>邮箱<input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label>密码<input type="password" required minLength={6} autoComplete={mode === "signin" ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          {message ? <p className="auth-message" role="status">{message}</p> : null}
          <button className="auth-submit" type="submit" disabled={busy}>{busy ? "处理中..." : mode === "signin" ? "进入工作台" : "创建账号"}</button>
        </form>
      </section>
    </main>
  );
}

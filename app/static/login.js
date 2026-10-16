/* Login page — Firebase Auth (Google + Email/Password). */
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.13.0/firebase-app.js";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  sendPasswordResetEmail,
} from "https://www.gstatic.com/firebasejs/10.13.0/firebase-auth.js";

const LS_TOKEN = "not.token";
const LS_USER = "not.user";
const $ = (id) => document.getElementById(id);

const cfg = window.NOT_FIREBASE_CONFIG;
if (!cfg || !cfg.apiKey) {
  document.body.innerHTML =
    '<div style="padding:24px;font-family:system-ui;color:#fff;background:#0f1115;min-height:100vh">' +
    '<h2>Firebase is not configured</h2>' +
    '<p>Open <code>app/static/firebase-config.js</code> and paste your Firebase web config.</p>' +
    '</div>';
  throw new Error("Missing Firebase config");
}

const app = initializeApp(cfg);
const auth = getAuth(app);

// NOTE: We intentionally do NOT redirect logged-in users here.
// The old onAuthStateChanged redirect caused an infinite loop when
// the backend token sync failed. Redirect happens only after a
// successful /api/auth/sync call in finishLogin().

function showError(el, msg) { el.textContent = msg; el.hidden = false; }
function hideError(el) { el.hidden = true; el.textContent = ""; }

const tabLogin = $("tabLogin");
const tabSignup = $("tabSignup");
const loginForm = $("loginForm");
const signupForm = $("signupForm");
const loginError = $("loginError");
const signupError = $("signupError");
const loginBtn = $("loginBtn");
const signupBtn = $("signupBtn");
const googleBtn = $("googleBtn");
const forgotBtn = $("forgotBtn");

function switchTab(which) {
  const isLogin = which === "login";
  tabLogin.classList.toggle("active", isLogin);
  tabSignup.classList.toggle("active", !isLogin);
  tabLogin.setAttribute("aria-selected", String(isLogin));
  tabSignup.setAttribute("aria-selected", String(!isLogin));
  loginForm.hidden = !isLogin;
  signupForm.hidden = isLogin;
  hideError(loginError);
  hideError(signupError);
}
tabLogin.addEventListener("click", () => switchTab("login"));
tabSignup.addEventListener("click", () => switchTab("signup"));

function friendly(err) {
  const code = err && err.code ? err.code : "";
  const map = {
    "auth/invalid-email": "That email doesn't look right.",
    "auth/user-disabled": "This account has been disabled.",
    "auth/user-not-found": "No account found with that email.",
    "auth/wrong-password": "Incorrect email or password.",
    "auth/invalid-credential": "Incorrect email or password.",
    "auth/invalid-login-credentials": "Incorrect email or password.",
    "auth/email-already-in-use": "That email is already registered. Try signing in.",
    "auth/weak-password": "Password must be at least 6 characters.",
    "auth/popup-closed-by-user": "Google sign-in was cancelled.",
    "auth/popup-blocked": "Your browser blocked the Google popup.",
    "auth/network-request-failed": "Network error. Check your connection.",
    "auth/too-many-requests": "Too many attempts. Wait a moment.",
    "auth/unauthorized-domain": "This domain is not authorized in Firebase. Add localhost in Firebase Console.",
    "auth/operation-not-allowed": "This sign-in method is not enabled in Firebase Console.",
  };
  return map[code] || (err && err.message) || "Something went wrong.";
}

async function finishLogin(fbUser) {
  const token = await fbUser.getIdToken(true);

  const res = await fetch("/api/auth/sync", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + token,
    },
    body: JSON.stringify({
      display_name: fbUser.displayName || null,
      photo_url: fbUser.photoURL || null,
    }),
  });

  if (!res.ok) {
    let detail = `Server error (${res.status})`;
    try { const j = await res.json(); if (j && j.detail) detail = j.detail; } catch {}
    throw new Error(detail);
  }

  const user = await res.json();
  localStorage.setItem(LS_TOKEN, token);
  localStorage.setItem(LS_USER, JSON.stringify(user));
  window.location.replace("/");
}

googleBtn.addEventListener("click", async () => {
  hideError(loginError);
  hideError(signupError);
  googleBtn.disabled = true;
  const original = googleBtn.innerHTML;
  googleBtn.innerHTML = "<span>Signing in…</span>";
  try {
    const provider = new GoogleAuthProvider();
    provider.setCustomParameters({ prompt: "select_account" });
    const cred = await signInWithPopup(auth, provider);
    await finishLogin(cred.user);
  } catch (err) {
    console.error("Google sign-in failed:", err);
    const msg = friendly(err);
    if (!signupForm.hidden) showError(signupError, msg);
    else showError(loginError, msg);
    googleBtn.disabled = false;
    googleBtn.innerHTML = original;
  }
});

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError(loginError);
  loginBtn.disabled = true;
  loginBtn.textContent = "Signing in…";
  try {
    const cred = await signInWithEmailAndPassword(
      auth, $("loginEmail").value.trim(), $("loginPassword").value
    );
    await finishLogin(cred.user);
  } catch (err) {
    console.error("Email sign-in failed:", err);
    showError(loginError, friendly(err));
    loginBtn.disabled = false;
    loginBtn.textContent = "Sign in";
  }
});

signupForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError(signupError);
  const email = $("signupEmail").value.trim();
  const pass = $("signupPassword").value;
  const conf = $("signupConfirm").value;
  if (pass !== conf) { showError(signupError, "Passwords do not match."); return; }
  if (pass.length < 6) { showError(signupError, "Password must be at least 6 characters."); return; }

  signupBtn.disabled = true;
  signupBtn.textContent = "Creating account…";
  try {
    const cred = await createUserWithEmailAndPassword(auth, email, pass);
    await finishLogin(cred.user);
  } catch (err) {
    console.error("Signup failed:", err);
    showError(signupError, friendly(err));
    signupBtn.disabled = false;
    signupBtn.textContent = "Create account";
  }
});

forgotBtn.addEventListener("click", async () => {
  hideError(loginError);
  const email = $("loginEmail").value.trim();
  if (!email) { showError(loginError, "Enter your email first."); return; }
  try {
    await sendPasswordResetEmail(auth, email);
    showError(loginError, "Password reset email sent. Check your inbox.");
    loginError.style.background = "rgba(62,207,142,0.12)";
    loginError.style.borderColor = "rgba(62,207,142,0.35)";
    loginError.style.color = "#7ee2b8";
  } catch (err) {
    showError(loginError, friendly(err));
  }
});
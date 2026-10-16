# NOT

A JARVIS-style AI assistant with a ChatGPT-inspired web UI.
FastAPI backend · vanilla JS frontend · OpenAI API · voice in and out.

---

## What it does

- Chat with an OpenAI model, with conversation history persisted in SQLite.
- Voice input via the browser's Web Speech API.
- Voice output via the browser's speech synthesis.
- Two voice modes: push-to-talk, and a hands-free conversation loop.
- Light and dark themes, English / Urdu / Roman Urdu / Hindi responses,
  RTL rendering for Urdu script, rename and delete conversations.
- API key stays entirely server-side.

## Honest limitations

- **Speech recognition is Chrome/Edge only.** Firefox has no
  `SpeechRecognition`. Safari support is partial. The UI shows a clear
  message when unsupported.
- **Browser TTS is not natural neural audio.** It uses the OS voices.
  Good enough for reading replies, not a replacement for real-time AI audio.
- **SQLite on Render's free tier is ephemeral.** Conversations are lost
  on redeploy. Use a paid plan with a mounted disk (see `render.yaml`),
  or swap in a managed database.
- **Microphone requires HTTPS.** `localhost` is the only exception.
  On any other host, the browser will refuse microphone access over HTTP.
- **In-memory rate limiting** does not survive restarts and is per-process.
  For multi-instance deploys, replace it with Redis or your host's limiter.
- **No authentication is included** beyond the optional `ACCESS_TOKEN`
  shared secret. Before going public, add real auth or set that token.

---

## Local setup (Windows 10/11 + VS Code)

### 1. Install Python
- Install **Python 3.10+** from https://www.python.org/downloads/windows/
- During install, tick **"Add Python to PATH"**.
- Verify in a fresh PowerShell:
  ```powershell
  python --version
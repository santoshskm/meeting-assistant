import json
import shutil
import subprocess
import threading
import urllib.request
import urllib.error

from PyQt6.QtCore import QObject, pyqtSignal

from config import (
    AI_BACKEND,
    CLAUDE_MODEL, CLAUDE_MODELS,
    OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_MODELS,
)

_SUMMARY_PROMPT = """You are a professional meeting analyst. Analyze the following meeting transcript and provide a structured report in clean markdown with these sections:

## Meeting Summary
A clear 2–3 paragraph overview of the discussion.

## Key Discussion Points
Bullet list of main topics covered.

## Decisions Made
Bullet list of any decisions reached. Write "None recorded" if none.

## Action Items
For each action item use this format:
- **Task:** [description]  **Owner:** [person or TBD]  **Deadline:** [date or TBD]  **Priority:** [High / Medium / Low]

## Follow-up Items
Things that need to be revisited. Write "None" if none.

---
TRANSCRIPT:
{transcript}"""


class AIProcessor(QObject):
    processing_started = pyqtSignal()
    summary_ready = pyqtSignal(str)
    processing_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.backend = AI_BACKEND          # "claude" or "ollama"
        self.model = CLAUDE_MODEL if AI_BACKEND == "claude" else OLLAMA_MODEL

    # --- public ---

    def get_available_models(self) -> list[str]:
        return list(CLAUDE_MODELS) if self.backend == "claude" else list(OLLAMA_MODELS)

    def get_backend(self) -> str:
        return self.backend

    def set_backend(self, backend: str):
        self.backend = backend
        self.model = CLAUDE_MODEL if backend == "claude" else OLLAMA_MODEL

    def generate_summary(self, transcript: str):
        if not transcript.strip():
            self.processing_error.emit("Transcript is empty — nothing to summarize.")
            return

        self.processing_started.emit()
        if self.backend == "claude":
            threading.Thread(target=self._run_claude, args=(transcript,), daemon=True).start()
        else:
            threading.Thread(target=self._run_ollama, args=(transcript,), daemon=True).start()

    # --- Claude CLI backend ---

    def _run_claude(self, transcript: str):
        claude_bin = shutil.which("claude")
        if not claude_bin:
            self.processing_error.emit(
                "Claude Code CLI not found.\n\n"
                "Install it with: npm install -g @anthropic-ai/claude-code\n"
                "Then run: claude login\n\n"
                "Or switch to Ollama backend in config.py (free, no account needed)."
            )
            return
        try:
            prompt = _SUMMARY_PROMPT.format(transcript=transcript)
            result = subprocess.run(
                [claude_bin, "-p", "--model", self.model],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode == 0 and result.stdout.strip():
                self.summary_ready.emit(result.stdout.strip())
            else:
                err = result.stderr.strip() or f"claude exited with code {result.returncode}"
                self.processing_error.emit(f"Claude CLI error:\n\n{err}")
        except subprocess.TimeoutExpired:
            self.processing_error.emit("Claude CLI timed out after 3 minutes.")
        except Exception as exc:
            self.processing_error.emit(str(exc))

    # --- Ollama backend ---

    def _run_ollama(self, transcript: str):
        url = f"{OLLAMA_BASE_URL}/api/generate"
        prompt = _SUMMARY_PROMPT.format(transcript=transcript)
        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }).encode()

        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode())
                text = data.get("response", "").strip()
                if text:
                    self.summary_ready.emit(text)
                else:
                    self.processing_error.emit("Ollama returned an empty response.")
        except urllib.error.URLError:
            self.processing_error.emit(
                "Cannot connect to Ollama.\n\n"
                "Make sure Ollama is installed and running:\n"
                "  ollama serve\n\n"
                "Download Ollama from: https://ollama.com"
            )
        except TimeoutError:
            self.processing_error.emit("Ollama timed out. Try a shorter transcript or a smaller model.")
        except Exception as exc:
            self.processing_error.emit(str(exc))

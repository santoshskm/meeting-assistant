import shutil
import subprocess
import threading

from PyQt6.QtCore import QObject, pyqtSignal

from config import CLAUDE_MODEL, CLAUDE_MODELS

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
        self.model = CLAUDE_MODEL

    # --- public ---

    def get_available_models(self) -> list[str]:
        return list(CLAUDE_MODELS)

    def generate_summary(self, transcript: str):
        if not transcript.strip():
            self.processing_error.emit("Transcript is empty — nothing to summarize.")
            return

        claude_bin = shutil.which("claude")
        if not claude_bin:
            self.processing_error.emit(
                "Claude Code CLI not found.\n\n"
                "Make sure 'claude' is installed and on your PATH."
            )
            return

        self.processing_started.emit()
        threading.Thread(
            target=self._run_generation,
            args=(transcript, claude_bin),
            daemon=True,
        ).start()

    # --- internal ---

    def _run_generation(self, transcript: str, claude_bin: str):
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
            self.processing_error.emit("Claude CLI timed out after 3 minutes. Try a shorter transcript.")
        except Exception as exc:
            self.processing_error.emit(str(exc))

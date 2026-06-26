from pathlib import Path

# Paths
TRANSCRIPT_DIR = Path("/Users/santoshmahto/Documents/Meeting Transcripts/Local_transcript")
EXPORTS_DIR = TRANSCRIPT_DIR / "exports"

# Whisper model: tiny | base | small | medium | large-v2
WHISPER_MODEL = "base"

# AI Backend: "claude" or "ollama"
AI_BACKEND = "claude"

# Claude (Anthropic) — requires Claude Code CLI installed and authenticated
CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_MODELS = [
    "claude-sonnet-4-6",
    "claude-opus-4-7",
    "claude-haiku-4-5-20251001",
]

# Ollama (free, local) — requires Ollama installed and running (ollama serve)
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3"
OLLAMA_MODELS = [
    "llama3",
    "llama3.2",
    "mistral",
    "phi3",
    "gemma",
    "qwen2",
]

# Audio
SAMPLE_RATE = 16000
CHUNK_DURATION = 30  # seconds per transcription chunk

# Meeting detection polling interval (seconds)
MEETING_CHECK_INTERVAL = 5

# Known meeting application process names (macOS)
MEETING_PROCESSES = {
    "Zoom": ["zoom.us", "zoom", "CptHost", "ZoomPhone"],
    "Microsoft Teams": ["Microsoft Teams", "MSTeams", "Teams"],
    "Webex": ["Cisco Webex Meetings", "webexmta", "Webex", "webex"],
    "Slack": ["Slack"],
    "Discord": ["Discord"],
    "Skype": ["Skype"],
    "FaceTime": ["FaceTime"],
    "GoToMeeting": ["GoToMeeting", "GoTo"],
    "BlueJeans": ["BlueJeans"],
    "Whereby": ["Whereby"],
}

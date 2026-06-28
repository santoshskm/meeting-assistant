from pathlib import Path

# Paths
TRANSCRIPT_DIR = Path.home() /"/Users/santoshkumarmahto/Documents/meeting-assistant"
EXPORTS_DIR = TRANSCRIPT_DIR / "exports"

# Whisper model: tiny | base | small | medium | large-v2
# "small" is the minimum recommended for Hindi/Hinglish accuracy
WHISPER_MODEL = "small"

# Transcription language
# "en" = English only, "hi" = Hindi only, None = auto-detect (best for Hinglish)
TRANSCRIPTION_LANGUAGE = "en"

# Claude (Anthropic) — set ANTHROPIC_API_KEY in your environment
CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_MODELS = [
    "claude-sonnet-4-6",
    "claude-opus-4-7",
    "claude-haiku-4-5-20251001",
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

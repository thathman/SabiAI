#!/usr/bin/env python3
"""bedtime_story.py — turn a story (written by Clawson in Daddy's warmth) into audio
in Hendrix's voice for his daughter in North Carolina.

The agent composes the story text (short, gentle, personal). This script does TTS via
ElevenLabs, saves the mp3, and logs it so it shows on the Bridge dashboard.

Usage:
  echo '{"title":"The Brave Little Lion","text":"Once upon a time...","voice_id":"<optional>"}' \
    | python3 bedtime_story.py
Set ELEVENLABS_VOICE_ID to Hendrix's cloned voice for the real magic. Returns the audio path.
"""
import json, os, sys, sqlite3, urllib.request
from datetime import datetime, date

DB = os.path.expanduser("~/.openclaw/workspace/data/bridge.db")
OUT = os.path.expanduser("~/.openclaw/workspace/data/bridge_stories")
API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
# Default = warm male ElevenLabs voice ("Josh"); override with the cloned "Daddy" voice.
DEFAULT_VOICE = os.environ.get("ELEVENLABS_VOICE_ID", "TxGEqnHWrfWFTfGW9XjX")

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_VOICE = os.environ.get("BEDTIME_OPENAI_VOICE", "onyx")  # warm deep male = "Daddy"

def synth_elevenlabs(text, voice_id):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    body = json.dumps({
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.3},
    }).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "xi-api-key": API_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def synth_openai(text):
    url = "https://api.openai.com/v1/audio/speech"
    body = json.dumps({"model": "tts-1", "voice": OPENAI_VOICE, "input": text}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def synth(text, voice_id):
    """Prefer ElevenLabs (cloned voice). Fall back to OpenAI TTS so it always works."""
    if API_KEY:
        try:
            return synth_elevenlabs(text, voice_id), "elevenlabs"
        except Exception:
            pass
    if OPENAI_KEY:
        return synth_openai(text), "openai"
    raise RuntimeError("no working TTS provider (set ELEVENLABS_API_KEY or OPENAI_API_KEY)")

def main():
    try:
        e = json.loads(sys.stdin.read())
    except Exception as ex:
        print(json.dumps({"ok": False, "error": f"bad JSON: {ex}"})); return
    text = (e.get("text") or "").strip()
    if not text:
        print(json.dumps({"ok": False, "error": "no story text"})); return
    os.makedirs(OUT, exist_ok=True)
    voice = e.get("voice_id") or DEFAULT_VOICE
    title = e.get("title", "Bedtime story")
    fname = f"{date.today().isoformat()}-{title[:30].replace(' ','_').replace('/','-')}.mp3"
    path = os.path.join(OUT, fname)
    try:
        audio, provider = synth(text, voice)
    except Exception as ex:
        print(json.dumps({"ok": False, "error": f"TTS failed: {ex}"})); return
    with open(path, "wb") as f:
        f.write(audio)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS stories(id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, title TEXT, text TEXT, audio_path TEXT, sent INTEGER DEFAULT 0)""")
    c.execute("INSERT INTO stories(date,title,text,audio_path) VALUES(?,?,?,?)",
              (date.today().isoformat(), title, text, path))
    c.commit(); c.close()
    print(json.dumps({"ok": True, "audio": path, "title": title,
                      "bytes": len(audio), "voice": provider}))

if __name__ == "__main__":
    main()

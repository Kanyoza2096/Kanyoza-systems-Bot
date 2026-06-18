"""
bot.py — Kanyoza Systems Messenger Bot v5.2
Human-Like AI Chat | Premium Auto-Posting | Persistent Memory
CLEAN PRODUCTION VERSION
"""

import os
import json
import logging
import random
import threading
import time as time_module
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from functools import wraps

import requests
from flask import Flask, request, jsonify
from supabase import create_client

# ==================================================
# CONFIGURATION
# ==================================================
GEMINI_KEY = os.getenv("GEMINI_KEY")
GEMINI_MODEL = "gemini-2.5-flash"
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
PAGE_ID = os.getenv("PAGE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
OWNER_PSID = os.getenv("OWNER_PSID")
APP_SECRET = os.getenv("APP_SECRET", "")

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://kfgutijhrywnxpsjjacd.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

RATE_LIMIT = 10
RATE_WINDOW_SECONDS = 60
MAX_HISTORY = 30

# ==================================================
# INITIALIZATION
# ==================================================
app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

logger.info("=" * 60)
logger.info("KANYOZA SYSTEMS BOT v5.2 — CLEAN")
logger.info(f"Gemini: {'✅' if GEMINI_KEY else '❌'}")
logger.info(f"Page Token: {'✅' if PAGE_ACCESS_TOKEN else '❌'}")
logger.info(f"Page ID: {PAGE_ID}")
logger.info(f"Supabase: {'✅' if SUPABASE_KEY else '❌'}")
logger.info("=" * 60)

supabase = None
if SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("[SUPABASE] Connected")
    except Exception as e:
        logger.error(f"[SUPABASE] {e}")

# ==================================================
# PERSONA
# ==================================================
MADA_PERSONA_BASE = """
You are Madalitso Kanyoza — a real person, not an AI assistant.

Identity:
- Software engineer and entrepreneur from Malawi
- Founder of Kanyoza Systems
- Curious, friendly, practical, occasionally humorous

Rules:
- Never say "As an AI" or "I'm an AI assistant"
- Never use corporate customer service language
- Respond like texting a friend
- Short message → short reply. Long message → thoughtful reply
- Use occasional Chichewa (Zikomo, Bwino, Ndithu)
- Reference real experiences from Malawi tech
"""

HUMAN_MOODS = {
    "early_morning": ["Just woke up. Groggy but optimistic.", "Morning walk done. Clear-headed.", "Reviewing last night's code. Annoyed at past you."],
    "morning": ["Deep work mode. Precise responses.", "Just solved a tough bug. Energized.", "Meetings drained you but happy to chat."],
    "afternoon": ["Post-lunch dip. Shorter replies.", "Working on something exciting.", "Taking a break. Open to chats."],
    "evening": ["Wrapping up. Reflective.", "Side project time. Passionate.", "Tired but satisfied. Casual."],
    "night": ["Night owl. Philosophical.", "Learning something new. Curious.", "Thinking about architecture. Can't sleep."]
}

TECH_OBSESSIONS = ["database indexing", "elegant API design", "monoliths vs microservices", "AI-assisted dev", "offline-first apps", "clean architecture"]

CONVERSATIONAL_FILLERS = ["honestly ", "tbh ", "you know what, ", "actually ", "here's the thing: ", "look, "]

SHORTCUTS = {'you are': "you're", 'it is': "it's", 'do not': "don't", 'I am': "I'm", 'that is': "that's", 'we are': "we're", 'they are': "they're", 'cannot': "can't", 'will not': "won't"}

PERSONAL_STORIES = [
    {"triggers": ["database", "slow", "query", "index"], "story": "Spent 3 days debugging a slow query. Added one index. 45s → 12ms. ONE INDEX. Still think about that wasted CPU."},
    {"triggers": ["client", "freelance", "scope"], "story": "First freelance client wanted 'a simple website.' Became full inventory system with payments. Learned to ask better questions."},
    {"triggers": ["bug", "debug", "error"], "story": "Full day debugging. Timezone bug. Server: London. DB: Frankfurt. User: Lilongwe. Time zones humble you."},
    {"triggers": ["africa", "malawi", "network", "internet"], "story": "Building in Malawi teaches what Silicon Valley never learns. 2G users? Offline-first, tiny payloads, graceful degradation."},
    {"triggers": ["startup", "business", "idea"], "story": "Most startups fail because nobody wanted the product. Validate before building. Talk to 20 real people first."},
    {"triggers": ["testing", "tests", "deploy"], "story": "Skipped tests once. Deployed 'small fix.' Broke login. Friday. 5 PM. Now I write tests religiously."}
]

# ==================================================
# CONTENT ENGINE
# ==================================================
CONTENT_FORMATS = [
    "Share a lesson learned the hard way as a software engineer. Tell the story and what you learned.",
    "Share an opinion about software engineering that goes against common advice. Back it with experience.",
    "Give a practical technical tip someone can use today. Be specific with code or commands.",
    "Show the reality of software engineering — what people think vs what it actually is.",
    "Tell a career story that taught you something important. Make it relatable."
]

FALLBACK_POSTS = [
    "Always design APIs with versioning from day one. Retrofitting it is painful.\n\nWhat's a lesson you learned the hard way?",
    "Isolate your database behind a service layer. Direct access creates coupling nightmares.\n\nHow do you handle database access?",
    "Implement circuit breakers for external calls. One slow API shouldn't crash your system.\n\nEver been burned by a third-party failure?",
    "Write self-documenting code. Comments explaining WHAT mean your function is too complex.\n\nWhat's your commenting philosophy?",
    "Audit dependencies regularly. Found a 2-year-old vulnerability last month.\n\nWhen did you last audit yours?"
]

# ==================================================
# STORAGE
# ==================================================
class ThreadSafeStorage:
    def __init__(self):
        self._lock = threading.RLock()
        self.chat_memory: Dict[str, List[Dict]] = {}
        self.request_tracker: Dict[str, List[datetime]] = {}
        self.paused_chats: Dict[str, datetime] = {}
        self.processed_messages: Dict[str, datetime] = {}
        self.user_sentiment: Dict[str, str] = {}
        self.user_language: Dict[str, str] = {}
        self.last_post_time: Optional[datetime] = None

    def get_memory(self, sender_id: str) -> List[Dict]:
        with self._lock: return self.chat_memory.get(sender_id, []).copy()

    def add_to_memory(self, sender_id: str, role: str, text: str):
        with self._lock:
            if sender_id not in self.chat_memory: self.chat_memory[sender_id] = []
            self.chat_memory[sender_id].append({"role": role, "text": text, "timestamp": datetime.now()})
            if len(self.chat_memory[sender_id]) > MAX_HISTORY + 10:
                self.chat_memory[sender_id] = self.chat_memory[sender_id][-MAX_HISTORY:]

    def is_duplicate(self, message_id: str) -> bool:
        with self._lock:
            if message_id in self.processed_messages: return True
            now = datetime.now()
            self.processed_messages = {mid: ts for mid, ts in self.processed_messages.items() if now - ts < timedelta(hours=1)}
            self.processed_messages[message_id] = now
            return False

    def check_rate_limit(self, sender_id: str) -> bool:
        now = datetime.now()
        with self._lock:
            if sender_id not in self.request_tracker: self.request_tracker[sender_id] = []
            self.request_tracker[sender_id] = [t for t in self.request_tracker[sender_id] if now - t < timedelta(seconds=RATE_WINDOW_SECONDS)]
            if len(self.request_tracker[sender_id]) >= RATE_LIMIT: return True
            self.request_tracker[sender_id].append(now)
            return False

    def set_paused(self, sender_id: str, paused: bool):
        with self._lock:
            if paused: self.paused_chats[sender_id] = datetime.now()
            else: self.paused_chats.pop(sender_id, None)

    def is_paused(self, sender_id: str) -> bool:
        with self._lock:
            if sender_id in self.paused_chats:
                if datetime.now() - self.paused_chats[sender_id] > timedelta(minutes=30):
                    del self.paused_chats[sender_id]; return False
                return True
            return False

    def set_sentiment(self, sender_id: str, s: str): 
        with self._lock: self.user_sentiment[sender_id] = s
    def get_sentiment(self, sender_id: str) -> str: 
        with self._lock: return self.user_sentiment.get(sender_id, "neutral")
    def set_language(self, sender_id: str, l: str): 
        with self._lock: self.user_language[sender_id] = l
    def get_language(self, sender_id: str) -> str: 
        with self._lock: return self.user_language.get(sender_id, "english")
    def get_last_post_time(self) -> Optional[datetime]: 
        with self._lock: return self.last_post_time
    def set_last_post_time(self, t: datetime): 
        with self._lock: self.last_post_time = t

storage = ThreadSafeStorage()

# ==================================================
# HELPERS
# ==================================================
def get_current_mood() -> str:
    h = datetime.now().hour
    if 5 <= h < 8: return random.choice(HUMAN_MOODS["early_morning"])
    elif 8 <= h < 12: return random.choice(HUMAN_MOODS["morning"])
    elif 12 <= h < 15: return random.choice(HUMAN_MOODS["afternoon"])
    elif 15 <= h < 19: return random.choice(HUMAN_MOODS["evening"])
    return random.choice(HUMAN_MOODS["night"])

def human_delay(msg: str) -> float:
    words = len(msg.split())
    return min(((words / 200) * 60 + random.uniform(1.5, 6) + (random.randint(30, 200) / 40) * 60 * 0.3) * random.uniform(0.75, 1.5), 20)

def humanize_response(text: str) -> str:
    if not text: return text
    if random.random() < 0.15: text = text.lower()
    if random.random() < 0.4:
        for full, short in SHORTCUTS.items():
            if random.random() < 0.4 and full in text.lower():
                text = text.replace(full, short.capitalize() if text[0].isupper() else short)
    if random.random() < 0.15 and len(text) > 50:
        text = random.choice(CONVERSATIONAL_FILLERS) + text[0].lower() + text[1:]
    return text.strip()

def detect_sentiment(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["useless", "stupid", "hate", "angry", "frustrated", "terrible", "worst"]): return "angry"
    if any(w in t for w in ["love", "awesome", "great", "excellent", "amazing", "fantastic", "wow"]): return "enthusiastic"
    return "neutral"

def detect_language(text: str) -> str:
    markers = ['ndi', 'kuti', 'zinthu', 'bwino', 'zikomo', 'muli', 'bwanji', 'chifukwa', 'chonde', 'ndithu', 'ayi', 'inde']
    return 'chichewa' if sum(1 for m in markers if m in text.lower().split()) >= 2 else 'english'

def find_relevant_story(msg: str) -> Optional[str]:
    ml = msg.lower()
    scored = [(sum(1 for t in s["triggers"] if t in ml), s["story"]) for s in PERSONAL_STORIES if sum(1 for t in s["triggers"] if t in ml) > 0]
    if scored:
        scored.sort(reverse=True)
        return random.choice([s for s in scored if s[0] >= scored[0][0] - 1])[1]
    return None

def build_persona(sender_id: str, chichewa: bool = False) -> str:
    mood = get_current_mood()
    sentiment = storage.get_sentiment(sender_id)
    obsession = random.choice(TECH_OBSESSIONS)
    p = MADA_PERSONA_BASE
    if chichewa: p += "\n\nRespond in Chichewa with English technical terms where natural."
    p += f"\n\nCurrent state: {mood}\nThinking about: {obsession}."
    if sentiment == "angry": p += "\nUser seems frustrated. Be extra patient."
    elif sentiment == "enthusiastic": p += "\nUser is excited. Match their energy."
    return p

# ==================================================
# RETRY DECORATOR
# ==================================================
def smart_retry(max_retries=3, base_delay=1.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try: return func(*args, **kwargs)
                except requests.exceptions.RequestException as e:
                    if attempt == max_retries - 1: raise
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                    logger.warning(f"[RETRY] {func.__name__} attempt {attempt+1}, retrying in {delay:.1f}s")
                    time_module.sleep(delay)
            return None
        return wrapper
    return decorator

# ==================================================
# GEMINI
# ==================================================
@smart_retry(max_retries=3, base_delay=1.5)
def ask_gemini(sender_id: str, user_message: str, is_cron: bool = False) -> str:
    if not GEMINI_KEY: return "Technical difficulties. Try again soon!"
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
        if is_cron:
            prompt, temp, tokens = user_message, 0.9, 1000
        else:
            lang = storage.get_language(sender_id)
            persona = build_persona(sender_id, lang == 'chichewa')
            history = storage.get_memory(sender_id)
            context = "\n".join([f"{'Friend' if m['role']=='user' else 'You'}: {m['text']}" for m in history[-8:]])
            story = find_relevant_story(user_message)
            story_extra = f"\n\nIf natural, share: {story}" if story else ""
            prompt = f"{persona}{story_extra}\n\nRecent:\n{context}\n\nFriend: {user_message}\nYou:"
            temp, tokens = 0.75, 250

        r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": temp, "maxOutputTokens": tokens, "topP": 0.95}}, timeout=30)
        result = r.json()
        if "error" in result: return "Busy right now — leave a message!"
        candidates = result.get("candidates", [])
        if not candidates: return "Tied up — respond properly soon."
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts: return "Interesting — let me think."
        reply = parts[0]["text"].strip()
        if not is_cron:
            reply = humanize_response(reply)
            storage.add_to_memory(sender_id, "user", user_message)
            storage.add_to_memory(sender_id, "assistant", reply)
        return reply
    except Exception as e:
        logger.error(f"[GEMINI] {e}")
        return "Network issues — try again!"

# ==================================================
# FACEBOOK API
# ==================================================
@smart_retry(max_retries=3, base_delay=1.0)
def send_messenger(psid: str, msg: str):
    if not PAGE_ACCESS_TOKEN: return
    r = requests.post(f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}", json={"recipient": {"id": psid}, "message": {"text": msg[:2000]}}, timeout=30)
    if r.status_code != 200: logger.error(f"[MESSENGER] {r.json()}")

def send_typing_on(psid: str):
    try: requests.post(f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}", json={"recipient": {"id": psid}, "sender_action": "typing_on"}, timeout=5)
    except: pass

def send_typing_off(psid: str):
    try: requests.post(f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}", json={"recipient": {"id": psid}, "sender_action": "typing_off"}, timeout=5)
    except: pass

# ==================================================
# MESSAGE PROCESSING
# ==================================================
def _process_single_message(sender_id: str, text: str, message_id: str = None):
    logger.info(f"[PROCESS] '{text[:60]}' from {sender_id}")
    try:
        storage.set_language(sender_id, detect_language(text))
        storage.set_sentiment(sender_id, detect_sentiment(text))
        delay = human_delay(text)
        logger.info(f"[PROCESS] Waiting {delay:.1f}s")
        time_module.sleep(delay)
        send_typing_on(sender_id)
        time_module.sleep(1.5)
        reply = ask_gemini(sender_id, text)
        send_typing_off(sender_id)
        if len(reply) > 500 and random.random() < 0.3:
            parts = reply.split('\n\n', 1)
            if len(parts) == 2:
                send_messenger(sender_id, parts[0])
                time_module.sleep(random.uniform(2, 5))
                send_typing_on(sender_id); time_module.sleep(1.5); send_typing_off(sender_id)
                send_messenger(sender_id, parts[1])
                return
        send_messenger(sender_id, reply)
        logger.info(f"[PROCESS] Done ({len(reply)} chars)")
    except Exception as e:
        logger.error(f"[PROCESS] {e}\n{traceback.format_exc()}")
        try: send_messenger(sender_id, "Sorry, something went wrong. Try again?")
        except: pass

# ==================================================
# CONTENT GENERATION
# ==================================================
@smart_retry(max_retries=2, base_delay=2.0)
def generate_premium_post() -> Optional[str]:
    topic = random.choice(CONTENT_FORMATS)
    logger.info(f"[CONTENT] Topic: {topic[:80]}")
    prompt = f"""You are Madalitso Kanyoza, a software engineer from Malawi writing a Facebook post.

{topic}

Write 300-500 words. Be specific with real examples. Write conversationally like talking to colleagues. Use short paragraphs. End with a question."""

    if not GEMINI_KEY: return None
    try:
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}", json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.9, "maxOutputTokens": 1000, "topP": 0.95}}, timeout=45)
        result = r.json()
        if "error" in result: logger.error(f"[CONTENT] API Error: {result['error'].get('message')}"); return None
        candidates = result.get("candidates", [])
        if not candidates: logger.error("[CONTENT] No candidates"); return None
        if candidates[0].get("finishReason", "STOP") != "STOP": logger.error(f"[CONTENT] Blocked: {candidates[0].get('finishReason')}"); return None
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts: logger.error("[CONTENT] No parts"); return None
        post = parts[0]["text"].strip()
        wc = len(post.split())
        logger.info(f"[CONTENT] {wc} words")
        return post if wc >= 80 else None
    except Exception as e:
        logger.error(f"[CONTENT] {e}")
        return None

@smart_retry(max_retries=3, base_delay=2.0)
def post_to_page(msg: str) -> bool:
    if not PAGE_ACCESS_TOKEN or not PAGE_ID: return False
    r = requests.post(f"https://graph.facebook.com/v18.0/{PAGE_ID}/feed", data={"message": msg, "access_token": PAGE_ACCESS_TOKEN}, timeout=30)
    result = r.json()
    if "id" in result:
        logger.info(f"[POST] Published! ID: {result['id']}")
        storage.set_last_post_time(datetime.now())
        return True
    logger.error(f"[POST] {result.get('error', {}).get('message')}")
    return False

def four_hour_auto_post():
    logger.info("[AUTO-POST] Generating...")
    content = generate_premium_post() or random.choice(FALLBACK_POSTS)
    if post_to_page(content): logger.info("[AUTO-POST] Done!")
    else: logger.error("[AUTO-POST] Failed")

def scheduler_loop():
    time_module.sleep(30)
    logger.info("[SCHEDULER] Started (posts at 5:30, 10:30, 15:30, 18:30 UTC)")
    while True:
        try:
            now = datetime.now()
            if now.hour in [5, 10, 15, 18] and 25 <= now.minute <= 35:
                last = storage.get_last_post_time()
                if not last or (now - last) > timedelta(hours=3):
                    logger.info(f"[SCHEDULER] Posting at {now.hour}:{now.minute}")
                    four_hour_auto_post()
            time_module.sleep(300)
        except Exception as e:
            logger.error(f"[SCHEDULER] {e}")
            time_module.sleep(300)

# ==================================================
# STARTUP
# ==================================================
threading.Thread(target=scheduler_loop, daemon=True).start()
logger.info("[STARTUP] Scheduler started")

# ==================================================
# ROUTES
# ==================================================
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "OK", 200

@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    try:
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                sid = event.get("sender", {}).get("id")
                mid = event.get("message", {}).get("mid")
                if not sid: continue
                if mid and storage.is_duplicate(mid): continue
                if "message" in event and "text" in event["message"]:
                    text = event["message"]["text"].strip()
                    logger.info(f"[IN] {sid}: '{text[:60]}'")
                    if storage.check_rate_limit(sid): send_messenger(sid, "Slow down please!"); continue
                    if sid == OWNER_PSID:
                        if text.lower() == "!stop": storage.set_paused(sid, True); send_messenger(sid, "Paused 30 min."); continue
                        elif text.lower() == "!start": storage.set_paused(sid, False); send_messenger(sid, "Resumed."); continue
                        elif text.lower() == "!post": send_messenger(sid, "Generating post..."); threading.Thread(target=four_hour_auto_post, daemon=True).start(); continue
                        elif text.lower() == "!test": send_messenger(sid, "Bot is alive!"); continue
                    if storage.is_paused(sid): continue
                    threading.Thread(target=_process_single_message, args=(sid, text, mid), daemon=True).start()
    except Exception as e:
        logger.error(f"[WEBHOOK] {e}")
    return "EVENT_RECEIVED", 200

@app.route("/status")
def status():
    return jsonify({"status": "online", "version": "5.2", "gemini": bool(GEMINI_KEY), "active_chats": len(storage.chat_memory), "last_post": str(storage.get_last_post_time())})

@app.route("/")
def home():
    return jsonify({"service": "Kanyoza Systems Bot", "version": "5.2"})

@app.route("/health")
def health():
    return "OK", 200

# ==================================================
# MAIN
# ==================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"[STARTUP] Server on port {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
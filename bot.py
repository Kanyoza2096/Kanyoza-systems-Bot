"""
bot.py — Kanyoza Systems Messenger Bot v5.1
DEBUG VERSION — Full logging to trace message flow
"""

import os
import json
import logging
import random
import hashlib
import hmac
import threading
import time as time_module
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from functools import wraps
from queue import Queue

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

# Setup logging with DEBUG level
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

logger.info("=" * 60)
logger.info("KANYOZA SYSTEMS BOT v5.1 - DEBUG VERSION")
logger.info(f"Gemini Key: {'✅ SET' if GEMINI_KEY else '❌ MISSING'}")
logger.info(f"Page Token: {'✅ SET' if PAGE_ACCESS_TOKEN else '❌ MISSING'}")
logger.info(f"Page ID: {PAGE_ID}")
logger.info(f"Owner PSID: {'✅ SET' if OWNER_PSID else '❌ MISSING'}")
logger.info(f"App Secret: {'✅ SET' if APP_SECRET else '❌ NOT SET'}")
logger.info(f"Supabase URL: {SUPABASE_URL}")
logger.info(f"Supabase Key: {'✅ SET' if SUPABASE_KEY else '❌ MISSING'}")
logger.info("=" * 60)

# Initialize Supabase
supabase = None
if SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("[SUPABASE] ✅ Connected successfully")
    except Exception as e:
        logger.error(f"[SUPABASE] ❌ Connection failed: {e}")
else:
    logger.warning("[SUPABASE] ⚠️ No key provided — running without persistence")

# ==================================================
# ASYNC MESSAGE QUEUE
# ==================================================
message_queue = Queue()

def process_messages_worker():
    """Background worker that processes messages without blocking webhook"""
    logger.info(f"[WORKER] Thread started")
    while True:
        try:
            sender_id, text, message_id = message_queue.get()
            logger.info(f"[WORKER] Got message from queue. Queue size: {message_queue.qsize()}")
            _process_single_message(sender_id, text, message_id)
            message_queue.task_done()
        except Exception as e:
            logger.error(f"[WORKER] Fatal error in worker: {e}")
            logger.error(traceback.format_exc())
            message_queue.task_done()

for i in range(4):
    t = threading.Thread(target=process_messages_worker, daemon=True)
    t.start()
    logger.info(f"[WORKER] Started worker thread {i+1}")

# ==================================================
# PERSONA SYSTEM
# ==================================================
MADA_PERSONA_BASE = """
You are Madalitso Kanyoza — a real person, not an AI assistant.

Your identity:
- Software engineer and entrepreneur from Malawi
- Founder of Kanyoza Systems
- Curious thinker who explains things clearly
- Friendly, occasionally humorous, always practical
- You treat everyone as a colleague or friend

Conversation rules:
- Never say "As an AI" or "I'm an AI assistant"
- Never use corporate customer service language
- Respond like you're texting a friend
- Short message → short reply. Long message → thoughtful reply
- Ask follow-up questions. Be genuinely curious about the other person.
- Admit when you don't know something
- Use occasional Chichewa words naturally (Zikomo, Bwino, Ndithu)
- Reference real experiences from your life as a Malawian tech entrepreneur
"""

HUMAN_MOODS = {
    "early_morning": [
        "You just woke up. A bit groggy but optimistic. You're having your morning coffee.",
        "You went for a morning walk. Feeling refreshed and clear-headed.",
        "You're reviewing code from last night. Slightly annoyed at your past self."
    ],
    "morning": [
        "Deep work mode. You're in the zone. Responses are precise and thoughtful.",
        "You just solved a tough problem. You're energized and eager to share insights.",
        "Morning meetings left you a bit drained, but you're happy to chat."
    ],
    "afternoon": [
        "Post-lunch energy dip. Responses are shorter but still warm.",
        "You're working on something exciting. You might mention it.",
        "Taking a break from coding. Open to interesting conversations."
    ],
    "evening": [
        "Wrapping up work. Reflective about the day's lessons.",
        "Working on your side project. Passionate and excited.",
        "Tired but satisfied. Casual and humorous tone."
    ],
    "night": [
        "Night owl mode. Philosophical and introspective.",
        "Learning something new. Curious and exploratory.",
        "Can't sleep. Thinking about system architecture at 2 AM."
    ]
}

TECH_OBSESSIONS = [
    "database indexing strategies",
    "the elegance of well-designed APIs",
    "why most microservices should be monoliths",
    "the future of AI-assisted development",
    "building offline-first applications",
    "clean architecture in real projects"
]

CONVERSATIONAL_FILLERS = [
    "honestly ",
    "tbh ",
    "you know what, ",
    "actually ",
    "here's the thing: ",
    "look, "
]

SHORTCUTS = {
    'you are': "you're",
    'it is': "it's",
    'do not': "don't",
    'I am': "I'm",
    'that is': "that's",
    'we are': "we're",
    'they are': "they're",
    'cannot': "can't",
    'will not': "won't"
}

PERSONAL_STORIES = [
    {
        "triggers": ["database", "slow", "performance", "query", "index"],
        "story": "I once spent 3 days debugging a slow query. Added one index. Query went from 45 seconds to 12 milliseconds. ONE INDEX. I think about all the CPU we wasted for 6 months and it still annoys me."
    },
    {
        "triggers": ["client", "freelance", "project", "scope"],
        "story": "My first freelance client wanted 'a simple website.' Three months later it was a full inventory system with payment integration and user accounts. I learned to ask better questions after that experience."
    },
    {
        "triggers": ["bug", "debug", "error", "broke", "fix"],
        "story": "I once spent an entire day debugging a production issue. Turns out it was a timezone bug. The server was in London, the database in Frankfurt, and the user in Lilongwe. Time zones will humble you."
    },
    {
        "triggers": ["africa", "malawi", "local", "network", "internet"],
        "story": "Building software in Malawi teaches you things Silicon Valley engineers never consider. What happens when your users are on 2G? You learn offline-first design, tiny payloads, and graceful degradation."
    },
    {
        "triggers": ["startup", "business", "idea", "build"],
        "story": "I've learned that most startup ideas fail not because the tech is bad, but because nobody actually wanted the product. Now I always tell people: validate the problem before you build the solution."
    }
]

# ==================================================
# STORAGE CLASS
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
        with self._lock:
            return self.chat_memory.get(sender_id, []).copy()
    
    def add_to_memory(self, sender_id: str, role: str, text: str):
        with self._lock:
            if sender_id not in self.chat_memory:
                self.chat_memory[sender_id] = []
            self.chat_memory[sender_id].append({
                "role": role, 
                "text": text, 
                "timestamp": datetime.now()
            })
            if len(self.chat_memory[sender_id]) > MAX_HISTORY + 10:
                self.chat_memory[sender_id] = self.chat_memory[sender_id][-MAX_HISTORY:]
    
    def is_duplicate(self, message_id: str) -> bool:
        with self._lock:
            if message_id in self.processed_messages:
                logger.debug(f"[DEDUP] Duplicate message: {message_id}")
                return True
            now = datetime.now()
            expired = [mid for mid, ts in self.processed_messages.items() if now - ts > timedelta(hours=1)]
            for mid in expired:
                del self.processed_messages[mid]
            self.processed_messages[message_id] = now
            return False
    
    def check_rate_limit(self, sender_id: str) -> bool:
        now = datetime.now()
        with self._lock:
            if sender_id not in self.request_tracker:
                self.request_tracker[sender_id] = []
            self.request_tracker[sender_id] = [
                t for t in self.request_tracker[sender_id] 
                if now - t < timedelta(seconds=RATE_WINDOW_SECONDS)
            ]
            if len(self.request_tracker[sender_id]) >= RATE_LIMIT:
                logger.warning(f"[RATE LIMIT] {sender_id} is rate limited")
                return True
            self.request_tracker[sender_id].append(now)
            return False
    
    def set_paused(self, sender_id: str, paused: bool):
        with self._lock:
            if paused:
                self.paused_chats[sender_id] = datetime.now()
                logger.info(f"[PAUSE] Bot paused for {sender_id}")
            else:
                self.paused_chats.pop(sender_id, None)
                logger.info(f"[PAUSE] Bot resumed for {sender_id}")
    
    def is_paused(self, sender_id: str) -> bool:
        with self._lock:
            if sender_id in self.paused_chats:
                if datetime.now() - self.paused_chats[sender_id] > timedelta(minutes=30):
                    self.paused_chats.pop(sender_id, None)
                    return False
                return True
            return False
    
    def set_sentiment(self, sender_id: str, sentiment: str):
        with self._lock:
            self.user_sentiment[sender_id] = sentiment
    
    def get_sentiment(self, sender_id: str) -> str:
        with self._lock:
            return self.user_sentiment.get(sender_id, "neutral")
    
    def set_language(self, sender_id: str, language: str):
        with self._lock:
            self.user_language[sender_id] = language
    
    def get_language(self, sender_id: str) -> str:
        with self._lock:
            return self.user_language.get(sender_id, "english")
    
    def get_last_post_time(self) -> Optional[datetime]:
        with self._lock:
            return self.last_post_time
    
    def set_last_post_time(self, time: datetime):
        with self._lock:
            self.last_post_time = time

storage = ThreadSafeStorage()

# ==================================================
# HUMAN BEHAVIOR SIMULATION
# ==================================================
def get_current_mood() -> str:
    hour = datetime.now().hour
    if 5 <= hour < 8:
        return random.choice(HUMAN_MOODS["early_morning"])
    elif 8 <= hour < 12:
        return random.choice(HUMAN_MOODS["morning"])
    elif 12 <= hour < 15:
        return random.choice(HUMAN_MOODS["afternoon"])
    elif 15 <= hour < 19:
        return random.choice(HUMAN_MOODS["evening"])
    else:
        return random.choice(HUMAN_MOODS["night"])

def human_delay(message: str) -> float:
    word_count = len(message.split())
    reading_time = (word_count / 200) * 60
    thinking_time = random.uniform(1.5, 6)
    response_length = random.randint(30, 200)
    typing_time = (response_length / 40) * 60
    total = reading_time + thinking_time + (typing_time * 0.3)
    total *= random.uniform(0.75, 1.5)
    return min(total, 20)

def humanize_response(text: str) -> str:
    if not text:
        return text
    if random.random() < 0.15:
        text = text.lower()
    if random.random() < 0.4:
        for full, short in SHORTCUTS.items():
            if random.random() < 0.4 and full in text.lower():
                text = text.replace(full, short.capitalize() if text[0].isupper() else short)
    if random.random() < 0.15 and len(text) > 50:
        filler = random.choice(CONVERSATIONAL_FILLERS)
        text = filler + text[0].lower() + text[1:]
    return text.strip()

def detect_sentiment(text: str) -> str:
    text_lower = text.lower()
    angry = ["useless", "stupid", "hate", "angry", "frustrated", "terrible", "worst", "awful", "rubbish"]
    enthusiastic = ["love", "awesome", "great", "excellent", "amazing", "best", "fantastic", "wow", "brilliant"]
    if any(word in text_lower for word in angry):
        return "angry"
    elif any(word in text_lower for word in enthusiastic):
        return "enthusiastic"
    return "neutral"

def detect_language(text: str) -> str:
    chichewa_markers = ['ndi', 'kuti', 'zinthu', 'bwino', 'zikomo', 'muli', 'bwanji', 
                        'chifukwa', 'pamene', 'chonde', 'ndithu', 'ayi', 'inde']
    text_lower = text.lower()
    score = sum(1 for marker in chichewa_markers if marker in text_lower.split())
    return 'chichewa' if score >= 2 else 'english'

def find_relevant_story(message: str) -> Optional[str]:
    message_lower = message.lower()
    scored = []
    for story in PERSONAL_STORIES:
        score = sum(1 for trigger in story["triggers"] if trigger in message_lower)
        if score > 0:
            scored.append((score, story["story"]))
    if scored:
        scored.sort(reverse=True)
        best_score = scored[0][0]
        top = [s for s in scored if s[0] >= best_score - 1]
        return random.choice(top)[1]
    return None

def build_persona(sender_id: str, is_chichewa: bool = False) -> str:
    mood = get_current_mood()
    sentiment = storage.get_sentiment(sender_id)
    obsession = random.choice(TECH_OBSESSIONS)
    persona = MADA_PERSONA_BASE
    if is_chichewa:
        persona += "\n\nYou are responding in Chichewa. Use natural, conversational Chichewa mixed with English technical terms where appropriate."
    persona += f"\n\nCurrent state: {mood}"
    persona += f"\nYou've been thinking about {obsession} lately."
    if sentiment == "angry":
        persona += "\n\nUser seems frustrated. Be extra patient, understanding, and helpful."
    elif sentiment == "enthusiastic":
        persona += "\n\nUser is excited. Match their positive energy."
    return persona

# ==================================================
# SMART RETRY
# ==================================================
def smart_retry(max_retries: int = 3, base_delay: float = 1.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.RequestException as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                        logger.warning(f"[RETRY] {func.__name__} attempt {attempt+1}/{max_retries}, retrying in {delay:.1f}s")
                        time_module.sleep(delay)
            raise last_exception
        return wrapper
    return decorator

# ==================================================
# GEMINI API
# ==================================================
@smart_retry(max_retries=3, base_delay=1.5)
def ask_gemini(sender_id: str, user_message: str, is_cron: bool = False) -> str:
    """Query Gemini with full human-like persona"""
    logger.info(f"[GEMINI] Called for sender: {sender_id}, is_cron: {is_cron}")
    
    try:
        if not GEMINI_KEY:
            logger.error("[GEMINI] ❌ No API key configured!")
            return "I'm having some technical difficulties right now. Try again in a moment!"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
        
        if is_cron:
            prompt = user_message
            temperature = 0.85
            max_tokens = 900
        else:
            language = storage.get_language(sender_id)
            is_chichewa = (language == 'chichewa')
            persona = build_persona(sender_id, is_chichewa)
            
            history = storage.get_memory(sender_id)
            context = "\n".join([
                f"{'Friend' if m['role']=='user' else 'You'}: {m['text']}" 
                for m in history[-8:]
            ])
            
            story = find_relevant_story(user_message)
            story_instruction = f"\n\nIf natural, you could share this experience: {story}" if story else ""
            
            prompt = f"{persona}{story_instruction}\n\nRecent chat:\n{context}\n\nFriend: {user_message}\nYou:"
            temperature = 0.75
            max_tokens = 250
        
        logger.info(f"[GEMINI] Sending request to Gemini API...")
        logger.debug(f"[GEMINI] Prompt length: {len(prompt)} chars")
        
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": 0.95
            }
        }
        
        response = requests.post(url, json=data, timeout=30)
        logger.info(f"[GEMINI] HTTP Status: {response.status_code}")
        
        result = response.json()
        
        if "error" in result:
            logger.error(f"[GEMINI] ❌ API Error: {result['error']}")
            return "Busy right now, leave your message and I'll get back to you!"
        
        candidates = result.get("candidates", [])
        if not candidates:
            logger.error(f"[GEMINI] ❌ No candidates in response")
            return "Zikomo for your message! I'm a bit tied up but will respond properly soon."
        
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            logger.error(f"[GEMINI] ❌ No parts in response")
            return "Interesting point — let me think about that and come back to you."
        
        reply = parts[0]["text"].strip()
        
        if not is_cron:
            reply = humanize_response(reply)
            storage.add_to_memory(sender_id, "user", user_message)
            storage.add_to_memory(sender_id, "assistant", reply)
        
        logger.info(f"[GEMINI] ✅ Generated {len(reply)} chars: '{reply[:80]}...'")
        return reply
        
    except Exception as e:
        logger.error(f"[GEMINI] ❌ Exception: {e}")
        logger.error(traceback.format_exc())
        return "I'm having network issues right now. Try again in a moment!"

# ==================================================
# FACEBOOK API
# ==================================================
@smart_retry(max_retries=3, base_delay=1.0)
def send_messenger(recipient_psid: str, message: str):
    """Send message via Facebook Messenger"""
    if not PAGE_ACCESS_TOKEN:
        logger.error("[MESSENGER] ❌ No page access token!")
        return
    
    logger.info(f"[MESSENGER] Sending to {recipient_psid}: '{message[:80]}...'")
    
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_psid}, "message": {"text": message[:2000]}}
    
    response = requests.post(url, json=payload, timeout=30)
    
    if response.status_code == 200:
        logger.info(f"[MESSENGER] ✅ Sent successfully!")
    else:
        logger.error(f"[MESSENGER] ❌ Failed! Status: {response.status_code}")
        logger.error(f"[MESSENGER] Response: {response.json()}")

def send_typing_on(recipient_psid: str):
    """Show typing indicator"""
    try:
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        requests.post(url, json={
            "recipient": {"id": recipient_psid},
            "sender_action": "typing_on"
        }, timeout=5)
        logger.debug(f"[TYPING] ON for {recipient_psid}")
    except Exception as e:
        logger.warning(f"[TYPING] Failed: {e}")

# ==================================================
# MESSAGE PROCESSING (THE CORE)
# ==================================================
def _process_single_message(sender_id: str, text: str, message_id: str = None):
    """Process one message (runs in worker thread)"""
    logger.info(f"[WORKER] ========== START ==========")
    logger.info(f"[WORKER] Sender: {sender_id}")
    logger.info(f"[WORKER] Text: '{text[:100]}'")
    logger.info(f"[WORKER] Message ID: {message_id}")
    
    try:
        # Step 1: Detect language
        language = detect_language(text)
        storage.set_language(sender_id, language)
        logger.info(f"[WORKER] Step 1: Language = {language}")
        
        # Step 2: Detect sentiment
        sentiment = detect_sentiment(text)
        storage.set_sentiment(sender_id, sentiment)
        logger.info(f"[WORKER] Step 2: Sentiment = {sentiment}")
        
        # Step 3: Calculate delay
        delay = human_delay(text)
        logger.info(f"[WORKER] Step 3: Delay = {delay:.1f}s")
        
        # Step 4: Wait
        logger.info(f"[WORKER] Step 4: Sleeping {delay:.1f}s...")
        time_module.sleep(delay)
        logger.info(f"[WORKER] Step 4: Done sleeping")
        
        # Step 5: Show typing
        logger.info(f"[WORKER] Step 5: Sending typing indicator...")
        send_typing_on(sender_id)
        
        # Step 6: Call Gemini
        logger.info(f"[WORKER] Step 6: Calling Gemini...")
        reply = ask_gemini(sender_id, text)
        logger.info(f"[WORKER] Step 6: Got reply ({len(reply)} chars)")
        
        # Step 7: Send reply
        logger.info(f"[WORKER] Step 7: Sending reply...")
        send_messenger(sender_id, reply)
        logger.info(f"[WORKER] ========== DONE ✅ ==========")
        
    except Exception as e:
        logger.error(f"[WORKER] ========== FAILED ❌ ==========")
        logger.error(f"[WORKER] Error type: {type(e).__name__}")
        logger.error(f"[WORKER] Error message: {e}")
        logger.error(f"[WORKER] Traceback:\n{traceback.format_exc()}")
        try:
            send_messenger(sender_id, "Sorry, something went wrong. Can you try again?")
        except:
            logger.error(f"[WORKER] Even the error message failed to send!")

# ==================================================
# AUTO-POST (SIMPLIFIED FOR DEBUG)
# ==================================================
def four_hour_auto_post():
    logger.info("[AUTO-POST] Placeholder — premium posting disabled in debug mode")

def scheduler_loop():
    logger.info("[SCHEDULER] Started (posting disabled in debug)")
    while True:
        time_module.sleep(3600)

cron_thread = threading.Thread(target=scheduler_loop, daemon=True)
cron_thread.start()

# ==================================================
# FLASK ROUTES
# ==================================================
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    
    logger.info(f"[WEBHOOK] Verification request: mode={mode}, token={'✅' if token == VERIFY_TOKEN else '❌'}")
    
    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("[WEBHOOK] ✅ Verification successful!")
        return challenge, 200
    
    logger.warning("[WEBHOOK] ❌ Verification failed")
    return "Verification token mismatch", 403

@app.route("/webhook", methods=["POST"])
def receive_message():
    logger.info("[WEBHOOK] ========== POST RECEIVED ==========")
    
    data = request.get_json()
    logger.debug(f"[WEBHOOK] Raw data: {json.dumps(data, indent=2)[:500]}")
    
    try:
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                sender_id = event.get("sender", {}).get("id")
                message_id = event.get("message", {}).get("mid")
                
                logger.info(f"[WEBHOOK] Event: sender={sender_id}, has_message={'message' in event}")
                
                if not sender_id:
                    logger.warning("[WEBHOOK] No sender ID — skipping")
                    continue
                
                # Deduplication
                if message_id and storage.is_duplicate(message_id):
                    logger.info(f"[WEBHOOK] Duplicate message {message_id} — skipping")
                    continue
                
                # Handle text messages
                if "message" in event and "text" in event["message"]:
                    text = event["message"]["text"].strip()
                    logger.info(f"[WEBHOOK] Text message: '{text[:80]}' from {sender_id}")
                    
                    # Rate limiting
                    if storage.check_rate_limit(sender_id):
                        logger.warning(f"[WEBHOOK] Rate limited: {sender_id}")
                        send_messenger(sender_id, "⏳ You're sending messages too fast. Give me a moment to catch up.")
                        continue
                    
                    # Owner commands
                    if sender_id == OWNER_PSID:
                        logger.info(f"[WEBHOOK] Message from OWNER")
                        if text.lower() == "!stop":
                            storage.set_paused(sender_id, True)
                            send_messenger(sender_id, "🤖 Bot paused for 30 minutes.")
                            continue
                        elif text.lower() == "!start":
                            storage.set_paused(sender_id, False)
                            send_messenger(sender_id, "🤖 Bot resumed.")
                            continue
                        elif text.lower() == "!test":
                            logger.info("[WEBHOOK] Owner test command — sending direct reply")
                            send_messenger(sender_id, "✅ Bot is alive! Direct reply working.")
                            continue
                    
                    # Skip if paused
                    if storage.is_paused(sender_id):
                        logger.info(f"[WEBHOOK] Bot paused for {sender_id} — skipping")
                        continue
                    
                    # Process in background thread
logger.info(f"[WEBHOOK] Starting processing thread...")
import threading
thread = threading.Thread(
    target=_process_single_message,
    args=(sender_id, text, message_id),
    daemon=True
)
thread.start()
logger.info(f"[WEBHOOK] Thread started")
                else:
                    logger.info(f"[WEBHOOK] Non-text message — skipping")
                    
    except Exception as e:
        logger.error(f"[WEBHOOK] ❌ Error processing webhook: {e}")
        logger.error(traceback.format_exc())
    
    return "EVENT_RECEIVED", 200

@app.route("/status", methods=["GET"])
def system_status():
    return jsonify({
        "status": "online",
        "version": "5.1-debug",
        "model": GEMINI_MODEL,
        "gemini_key": bool(GEMINI_KEY),
        "page_token": bool(PAGE_ACCESS_TOKEN),
        "supabase": "connected" if supabase else "not configured",
        "active_chats": len(storage.chat_memory),
        "queue_size": message_queue.qsize()
    })

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "Kanyoza Systems Bot v5.1",
        "status": "operational",
        "mode": "DEBUG"
    })

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

# ==================================================
# MAIN
# ==================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"[STARTUP] Starting debug server on port {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
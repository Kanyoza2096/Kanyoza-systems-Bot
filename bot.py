"""
bot.py — Kanyoza Systems Messenger Bot v5.1
Human-Like AI Chat | Premium Auto-Posting | Persistent Memory
PRODUCTION VERSION — All features enabled
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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

logger.info("=" * 60)
logger.info("KANYOZA SYSTEMS BOT v5.1 — PRODUCTION")
logger.info(f"Gemini Key: {'✅' if GEMINI_KEY else '❌'}")
logger.info(f"Page Token: {'✅' if PAGE_ACCESS_TOKEN else '❌'}")
logger.info(f"Page ID: {PAGE_ID}")
logger.info(f"Owner PSID: {'✅' if OWNER_PSID else '❌'}")
logger.info(f"Supabase: {'✅' if SUPABASE_KEY else '❌ (disabled)'}")
logger.info("=" * 60)

# Initialize Supabase
supabase = None
if SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("[SUPABASE] ✅ Connected")
    except Exception as e:
        logger.error(f"[SUPABASE] ❌ {e}")

# ==================================================
# PERSONA & HUMAN BEHAVIOR
# ==================================================
MADA_PERSONA_BASE = """
You are Madalitso Kanyoza — a real person, not an AI assistant.

Your identity:
- Software engineer and entrepreneur from Malawi
- Founder of Kanyoza Systems
- Curious thinker who explains things clearly
- Friendly, occasionally humorous, always practical

Conversation rules:
- Never say "As an AI" or "I'm an AI assistant"
- Never use corporate customer service language
- Respond like you're texting a friend
- Short message → short reply. Long message → thoughtful reply
- Ask follow-up questions. Be genuinely curious.
- Use occasional Chichewa words naturally (Zikomo, Bwino, Ndithu)
- Reference real experiences from Malawi tech scene
"""

HUMAN_MOODS = {
    "early_morning": [
        "You just woke up. Groggy but optimistic. Having coffee.",
        "Morning walk done. Feeling refreshed and clear-headed.",
        "Reviewing last night's code. Slightly annoyed at past you."
    ],
    "morning": [
        "Deep work mode. Precise and thoughtful responses.",
        "Just solved a tough bug. Energized and eager to share.",
        "Meetings drained you but you're happy to chat."
    ],
    "afternoon": [
        "Post-lunch dip. Shorter but still warm replies.",
        "Working on something exciting. You might mention it.",
        "Taking a coding break. Open to interesting chats."
    ],
    "evening": [
        "Wrapping up. Reflective about the day.",
        "Side project time. Passionate and excited.",
        "Tired but satisfied. Casual and humorous."
    ],
    "night": [
        "Night owl mode. Philosophical and introspective.",
        "Learning something new. Curious and exploratory.",
        "Thinking about architecture at 2 AM. Can't sleep."
    ]
}

TECH_OBSESSIONS = [
    "database indexing strategies",
    "elegant API design",
    "why microservices should be monoliths",
    "AI-assisted development",
    "offline-first applications",
    "clean architecture patterns"
]

CONVERSATIONAL_FILLERS = [
    "honestly ", "tbh ", "you know what, ",
    "actually ", "here's the thing: ", "look, "
]

SHORTCUTS = {
    'you are': "you're", 'it is': "it's", 'do not': "don't",
    'I am': "I'm", 'that is': "that's", 'we are': "we're",
    'they are': "they're", 'cannot': "can't", 'will not': "won't"
}

PERSONAL_STORIES = [
    {
        "triggers": ["database", "slow", "performance", "query", "index"],
        "story": "I once spent 3 days debugging a slow query. Added one index. Query went from 45 seconds to 12 milliseconds. ONE INDEX. I still think about all that wasted CPU."
    },
    {
        "triggers": ["client", "freelance", "project", "scope"],
        "story": "My first freelance client wanted 'a simple website.' Three months later: full inventory system with payment integration. I learned to ask better questions."
    },
    {
        "triggers": ["bug", "debug", "error", "broke"],
        "story": "I spent an entire day debugging a production issue. Turned out to be a timezone bug. Server in London, database in Frankfurt, user in Lilongwe. Time zones will humble you."
    },
    {
        "triggers": ["africa", "malawi", "local", "network", "internet"],
        "story": "Building in Malawi teaches you things Silicon Valley never considers. What happens on 2G? You learn offline-first, tiny payloads, graceful degradation. It makes you better."
    },
    {
        "triggers": ["startup", "business", "idea", "build"],
        "story": "Most startups fail because nobody wanted the product. Not because the tech was bad. I always say: validate the problem before building the solution. Talk to 20 real people first."
    },
    {
        "triggers": ["testing", "tests", "deploy", "broke"],
        "story": "I used to skip tests. Then I deployed a 'small fix' that broke login. On a Friday. At 5 PM. Now I write tests religiously. Learn from my pain."
    }
]

# ==================================================
# CONTENT ENGINE
# ==================================================
CONTENT_HOOKS = [
    "I cost a client $50,000 with one bad architectural decision. Here's what I learned:",
    "I almost lost my biggest client last year. The reason was embarrassing.",
    "Clean Code is overrated and I'm tired of pretending it's not.",
    "Your microservices are probably making your life harder.",
    "The best debugging tool isn't a debugger. It's something much simpler.",
    "I fixed a 3-week bug in 30 seconds. The solution will annoy you.",
    "Here's a pattern that saved me 100 hours of refactoring:",
    "Stop writing complex code. One principle changed everything.",
    "One database setting. That's all it took to make our app 10x faster.",
    "Building software in Malawi taught me something Silicon Valley never learns.",
    "I've interviewed 50 developers. Here's what separates good from great:",
    "Your error messages are terrible and costing you users. Here's the fix:"
]

CONTENT_FORMATS = {
    "lessons_learned": """Write a Facebook post about a lesson you learned the hard way as a software engineer.
Start with this hook: '{hook}'
Then tell the story (3-4 sentences).
Then share 3-5 specific lessons.
End with a question for your audience.
Write 400-600 words. Be conversational. Be specific.""",
    
    "controversial_take": """Write a Facebook post sharing an opinion about software engineering that challenges conventional thinking.
Start with this hook: '{hook}'
State your opinion clearly.
Give 2-3 examples from your experience.
Acknowledge when the other side has a point.
End by asking readers for their opinion.
Write 300-500 words. Be confident but open to discussion.""",
    
    "quick_win": """Write a short Facebook post sharing a useful technical tip.
Start with this hook: '{hook}'
Describe a specific problem.
Give the solution with specific details.
Briefly explain why it works.
Write 200-300 words. Make it immediately useful.""",
    
    "behind_the_scenes": """Write a Facebook post showing what software engineering is really like.
Start with this hook: '{hook}'
Describe what people think the job is.
Describe what it actually is, with a real example.
End with why this matters.
Write 300-500 words. Be honest and relatable.""",
    
    "story_lesson": """Write a Facebook post telling a story from your career as a software engineer.
Start with this hook: '{hook}'
Tell the full story: what happened, what went wrong, what you learned.
End with a universal lesson.
Write 400-600 words. Make readers feel like they were there."""
}

FALLBACK_POSTS = [
    "Always design APIs with versioning from day one. Retrofitting it is painful.\n\nWhat's a lesson you learned the hard way?",
    "Isolate your database behind a service layer. Direct access creates coupling nightmares.\n\nHow do you handle database access in your architecture?",
    "Implement circuit breakers for external calls. One slow API shouldn't crash your system.\n\nEver been burned by a third-party failure?",
    "Write self-documenting code. Comments explaining WHAT mean your function is too complex.\n\nWhat's your code commenting philosophy?",
    "Audit your dependencies regularly. Found a 2-year-old vulnerability last month.\n\nWhen did you last audit yours?"
]

# ==================================================
# THREAD-SAFE STORAGE
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
                "role": role, "text": text, "timestamp": datetime.now()
            })
            if len(self.chat_memory[sender_id]) > MAX_HISTORY + 10:
                self.chat_memory[sender_id] = self.chat_memory[sender_id][-MAX_HISTORY:]
    
    def is_duplicate(self, message_id: str) -> bool:
        with self._lock:
            if message_id in self.processed_messages:
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
                return True
            self.request_tracker[sender_id].append(now)
            return False
    
    def set_paused(self, sender_id: str, paused: bool):
        with self._lock:
            if paused:
                self.paused_chats[sender_id] = datetime.now()
            else:
                self.paused_chats.pop(sender_id, None)
    
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
# HELPER FUNCTIONS
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
    typing_time = (random.randint(30, 200) / 40) * 60
    total = reading_time + thinking_time + (typing_time * 0.3)
    return min(total * random.uniform(0.75, 1.5), 20)

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
    angry = ["useless", "stupid", "hate", "angry", "frustrated", "terrible", "worst", "awful"]
    enthusiastic = ["love", "awesome", "great", "excellent", "amazing", "best", "fantastic", "wow"]
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
        top = [s for s in scored if s[0] >= scored[0][0] - 1]
        return random.choice(top)[1]
    return None

def build_persona(sender_id: str, is_chichewa: bool = False) -> str:
    mood = get_current_mood()
    sentiment = storage.get_sentiment(sender_id)
    obsession = random.choice(TECH_OBSESSIONS)
    persona = MADA_PERSONA_BASE
    if is_chichewa:
        persona += "\n\nRespond in Chichewa with English technical terms where appropriate."
    persona += f"\n\nCurrent state: {mood}"
    persona += f"\nYou've been thinking about {obsession} lately."
    if sentiment == "angry":
        persona += "\n\nUser seems frustrated. Be extra patient and helpful."
    elif sentiment == "enthusiastic":
        persona += "\n\nUser is excited. Match their energy."
    return persona

# ==================================================
# SMART RETRY DECORATOR
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
    try:
        if not GEMINI_KEY:
            return "I'm having technical difficulties. Try again soon!"

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
            story_instruction = f"\n\nIf natural, share this: {story}" if story else ""
            prompt = f"{persona}{story_instruction}\n\nRecent chat:\n{context}\n\nFriend: {user_message}\nYou:"
            temperature = 0.75
            max_tokens = 250
        
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": 0.95
            }
        }
        
        response = requests.post(url, json=data, timeout=30)
        result = response.json()
        
        if "error" in result:
            logger.error(f"[GEMINI] API Error: {result['error']}")
            return "Busy right now, leave a message and I'll get back!"

        candidates = result.get("candidates", [])
        if not candidates:
            return "Zikomo! I'm a bit tied up — respond properly soon."

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return "Interesting — let me think about that."

        reply = parts[0]["text"].strip()
        
        if not is_cron:
            reply = humanize_response(reply)
            storage.add_to_memory(sender_id, "user", user_message)
            storage.add_to_memory(sender_id, "assistant", reply)
        
        return reply
        
    except Exception as e:
        logger.error(f"[GEMINI] Exception: {e}")
        return "Network issues — try again shortly!"

# ==================================================
# FACEBOOK MESSENGER API
# ==================================================
@smart_retry(max_retries=3, base_delay=1.0)
def send_messenger(recipient_psid: str, message: str):
    if not PAGE_ACCESS_TOKEN:
        logger.error("[MESSENGER] No page token!")
        return
    
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_psid}, "message": {"text": message[:2000]}}
    response = requests.post(url, json=payload, timeout=30)
    
    if response.status_code != 200:
        logger.error(f"[MESSENGER] Failed: {response.json()}")

def send_typing_on(recipient_psid: str):
    try:
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        requests.post(url, json={
            "recipient": {"id": recipient_psid},
            "sender_action": "typing_on"
        }, timeout=5)
    except:
        pass

def send_typing_off(recipient_psid: str):
    try:
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        requests.post(url, json={
            "recipient": {"id": recipient_psid},
            "sender_action": "typing_off"
        }, timeout=5)
    except:
        pass

# ==================================================
# MESSAGE PROCESSING
# ==================================================
def _process_single_message(sender_id: str, text: str, message_id: str = None):
    """Process one message with full human-like behavior"""
    logger.info(f"[PROCESS] Processing: '{text[:60]}' from {sender_id}")
    
    try:
        # Detect language
        language = detect_language(text)
        storage.set_language(sender_id, language)
        
        # Detect sentiment
        sentiment = detect_sentiment(text)
        storage.set_sentiment(sender_id, sentiment)
        
        # Human-like delay (reading + thinking)
        delay = human_delay(text)
        logger.info(f"[PROCESS] Waiting {delay:.1f}s (human-like delay)")
        time_module.sleep(delay)
        
        # Show typing indicator
        send_typing_on(sender_id)
        
        # Get AI response
        reply = ask_gemini(sender_id, text)
        
        # Stop typing
        send_typing_off(sender_id)
        
        # Sometimes split long messages (feels more human)
        if len(reply) > 500 and random.random() < 0.3:
            parts = reply.split('\n\n', 1)
            if len(parts) == 2:
                send_messenger(sender_id, parts[0])
                time_module.sleep(random.uniform(2, 5))
                send_typing_on(sender_id)
                time_module.sleep(random.uniform(1, 3))
                send_typing_off(sender_id)
                send_messenger(sender_id, parts[1])
                logger.info(f"[PROCESS] Sent as 2 messages")
                return
        
        # Send response
        send_messenger(sender_id, reply)
        logger.info(f"[PROCESS] ✅ Reply sent ({len(reply)} chars)")
        
    except Exception as e:
        logger.error(f"[PROCESS] ❌ Failed: {e}")
        logger.error(traceback.format_exc())
        try:
            send_messenger(sender_id, "Sorry, something went wrong. Try again?")
        except:
            pass

# ==================================================
# PREMIUM CONTENT GENERATION
# ==================================================
@smart_retry(max_retries=2, base_delay=2.0)
def generate_premium_post() -> Optional[str]:
    hook = random.choice(CONTENT_HOOKS)
    format_name = random.choice(list(CONTENT_FORMATS.keys()))
    format_instructions = CONTENT_FORMATS[format_name].replace('{hook}', hook)
    
    logger.info(f"[CONTENT] Generating {format_name} post...")
    
    prompt = f"""You are Madalitso Kanyoza, a senior software engineer from Malawi.

{format_instructions}

Critical rules:
- Sound like a real person sharing hard-earned wisdom
- Be specific. Real numbers, real tools, real scenarios.
- No motivational fluff. No "follow your dreams."
- Technical enough to be useful, accessible enough to be readable.
- Never use "in today's digital age" or "leveraging synergies."
- Make people want to save this post."""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
        response = requests.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
       "generationConfig": {"temperature": 0.85, "maxOutputTokens": 2000, "topP": 0.95}
        }, timeout=45)
        result = response.json()
        
        if result.get("candidates"):
            post = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            word_count = len(post.split())
            logger.info(f"[CONTENT] ✅ {word_count} words ({format_name})")
            if word_count >= 100:
                return post
        
        return None
    except Exception as e:
        logger.error(f"[CONTENT] ❌ {e}")
        return None

def get_fallback_post() -> str:
    return random.choice(FALLBACK_POSTS)

@smart_retry(max_retries=3, base_delay=2.0)
def post_to_page(message: str) -> bool:
    if not PAGE_ACCESS_TOKEN or not PAGE_ID:
        logger.error("[POST] Missing credentials")
        return False
    
    url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/feed"
    payload = {"message": message, "access_token": PAGE_ACCESS_TOKEN}
    response = requests.post(url, data=payload, timeout=30)
    result = response.json()
    
    if "id" in result:
        logger.info(f"[POST] ✅ Published! ID: {result['id']}")
        storage.set_last_post_time(datetime.now())
        return True
    
    logger.error(f"[POST] ❌ {result.get('error', {}).get('message')}")
    return False

def four_hour_auto_post():
    """Generate and publish a premium post"""
    logger.info("[AUTO-POST] Generating...")
    
    post_content = generate_premium_post()
    if not post_content:
        logger.info("[AUTO-POST] Using fallback")
        post_content = get_fallback_post()
    
    success = post_to_page(post_content)
    if success:
        logger.info("[AUTO-POST] ✅ Published!")
    else:
        logger.error("[AUTO-POST] ❌ Failed")

def scheduler_loop():
    """Post at optimal times: 7:30, 12:30, 17:30, 20:30 CAT"""
    time_module.sleep(30)
    logger.info("[SCHEDULER] ✅ Started (posts at 5:30, 10:30, 15:30, 18:30 UTC)")
    
    while True:
        try:
            now = datetime.now()
            hour, minute = now.hour, now.minute
            
            # Check if optimal posting time (within 5 min window)
            if hour in [5, 10, 15, 18] and 25 <= minute <= 35:
                last = storage.get_last_post_time()
                if not last or (now - last) > timedelta(hours=3):
                    logger.info(f"[SCHEDULER] 🕐 Posting time! {hour}:{minute}")
                    four_hour_auto_post()
            
            time_module.sleep(300)  # Check every 5 min
            
        except Exception as e:
            logger.error(f"[SCHEDULER] ❌ {e}")
            time_module.sleep(300)

# ==================================================
# START BACKGROUND THREADS
# ==================================================
scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
scheduler_thread.start()
logger.info("[STARTUP] Scheduler thread started")

# ==================================================
# FLASK ROUTES
# ==================================================
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    if request.args.get("hub.mode") == "subscribe":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Verification failed", 403
    return "OK", 200

@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    
    try:
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                sender_id = event.get("sender", {}).get("id")
                message_id = event.get("message", {}).get("mid")
                
                if not sender_id:
                    continue
                
                # Deduplication
                if message_id and storage.is_duplicate(message_id):
                    continue
                
                if "message" in event and "text" in event["message"]:
                    text = event["message"]["text"].strip()
                    logger.info(f"[INBOUND] {sender_id}: '{text[:60]}'")
                    
                    # Rate limiting
                    if storage.check_rate_limit(sender_id):
                        send_messenger(sender_id, "⏳ Slow down please!")
                        continue
                    
                    # Owner commands
                    if sender_id == OWNER_PSID:
                        if text.lower() == "!stop":
                            storage.set_paused(sender_id, True)
                            send_messenger(sender_id, "🤖 Bot paused for 30 min.")
                            continue
                        elif text.lower() == "!start":
                            storage.set_paused(sender_id, False)
                            send_messenger(sender_id, "🤖 Bot resumed.")
                            continue
                        elif text.lower() == "!post":
                            send_messenger(sender_id, "⚙️ Generating premium post...")
                            threading.Thread(target=four_hour_auto_post, daemon=True).start()
                            continue
                        elif text.lower() == "!test":
                            send_messenger(sender_id, "✅ Bot is alive and working!")
                            continue
                    
                    # Skip if paused
                    if storage.is_paused(sender_id):
                        continue
                    
                    # Process in background thread
                    threading.Thread(
                        target=_process_single_message,
                        args=(sender_id, text, message_id),
                        daemon=True
                    ).start()
                    
    except Exception as e:
        logger.error(f"[WEBHOOK] Error: {e}")
    
    return "EVENT_RECEIVED", 200

@app.route("/status", methods=["GET"])
def system_status():
    return jsonify({
        "status": "online",
        "version": "5.1",
        "model": GEMINI_MODEL,
        "gemini": bool(GEMINI_KEY),
        "facebook": bool(PAGE_ACCESS_TOKEN),
        "supabase": bool(supabase),
        "active_chats": len(storage.chat_memory),
        "last_post": str(storage.get_last_post_time())
    })

@app.route("/", methods=["GET"])
def home():
    return jsonify({"service": "Kanyoza Systems Bot", "version": "5.1"})

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

# ==================================================
# MAIN
# ==================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"[STARTUP] Server starting on port {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
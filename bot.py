"""
bot.py — Kanyoza Systems Messenger Bot v4.0
Gemini 2.5 Flash | 4-Hour Professional Posts | AI Chat
"""

import os
import logging
import random
import hashlib
import hmac
import threading
import time as time_module
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from functools import wraps

import requests
from flask import Flask, request, jsonify

# ==================================================
# CONFIGURATION
# ==================================================
GEMINI_KEY = os.getenv("GEMINI_KEY")
GEMINI_MODEL = "gemini-2.5-flash"
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
PAGE_ID = os.getenv("PAGE_ID", "1237042419481977")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "my_secret_token_123")
OWNER_PSID = os.getenv("OWNER_PSID")
APP_SECRET = os.getenv("APP_SECRET", "")

RATE_LIMIT = 10
RATE_WINDOW_SECONDS = 60
MAX_HISTORY = 30

# Create Flask app FIRST (before any routes)
app = Flask(__name__)

# ==================================================
# LOGGING - FIXED SYNTAX
# ==================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

logger.info("=" * 60)
logger.info("KANYOZA SYSTEMS BOT v4.0 - Gemini 2.5 Flash")

# FIXED: Proper f-string syntax
gemini_status = "✅ SET" if GEMINI_KEY else "❌ MISSING"
page_token_status = "✅ SET" if PAGE_ACCESS_TOKEN else "❌ MISSING"
owner_status = "✅ SET" if OWNER_PSID else "❌ MISSING"

logger.info(f"Gemini Key: {gemini_status}")
logger.info(f"Page Token: {page_token_status}")
logger.info(f"Page ID: {PAGE_ID}")
logger.info(f"Owner PSID: {owner_status}")
logger.info(f"Model: {GEMINI_MODEL}")
logger.info("=" * 60)

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
                now = datetime.now()
                expired = [mid for mid, ts in self.processed_messages.items() 
                          if now - ts > timedelta(hours=1)]
                for mid in expired:
                    del self.processed_messages[mid]
                return True
            self.processed_messages[message_id] = datetime.now()
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
    
    def get_last_post_time(self) -> Optional[datetime]:
        with self._lock:
            return self.last_post_time
    
    def set_last_post_time(self, time: datetime):
        with self._lock:
            self.last_post_time = time
    
    def get_stats(self) -> dict:
        with self._lock:
            return {
                "active_conversations": len(self.chat_memory),
                "paused_chats": len(self.paused_chats),
                "unique_users": len(self.chat_memory)
            }
    
    def get_recent_users(self, limit: int = 50) -> List[str]:
        with self._lock:
            return list(self.chat_memory.keys())[:limit]

storage = ThreadSafeStorage()

# ==================================================
# PERSONA
# ==================================================
MADA_PERSONA_BASE = """
You are Madalitso, a professional yet witty software engineer from Malawi.
You represent Kanyoza Systems — a respected tech company.

RULES:
1. PRIMARY LANGUAGE: English always (professional tech context)
2. Chichewa allowed only for: "Moni", "Zikomo", "Bho" — never full sentences
3. Keep replies SHORT (1-2 sentences for casual, 3-4 for technical questions)
4. Be friendly, knowledgeable, slightly sarcastic but never rude
5. If technical question: Give clear, accurate answer
6. If unsure: "That data is currently unavailable. Check back later!"
7. Never sound robotic or like customer service
"""

def get_persona_with_sentiment(sentiment: str) -> str:
    if sentiment == "angry":
        return MADA_PERSONA_BASE + "\n\nUser seems frustrated. Respond with extra patience and offer specific help."
    elif sentiment == "enthusiastic":
        return MADA_PERSONA_BASE + "\n\nUser is excited. Match their positive energy."
    return MADA_PERSONA_BASE

def detect_sentiment(text: str) -> str:
    text_lower = text.lower()
    angry_patterns = ["useless", "stupid", "hate", "angry", "frustrated", "terrible", "worst", "awful"]
    enthusiastic_patterns = ["love", "awesome", "great", "excellent", "amazing", "best", "fantastic"]
    
    if any(word in text_lower for word in angry_patterns):
        return "angry"
    elif any(word in text_lower for word in enthusiastic_patterns):
        return "enthusiastic"
    return "neutral"

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
                        logger.warning(f"[RETRY] Attempt {attempt+1}/{max_retries} failed, retrying in {delay:.1f}s")
                        time_module.sleep(delay)
            raise last_exception
        return wrapper
    return decorator

# ==================================================
# TYPING INDICATOR
# ==================================================
def send_typing_action(recipient_psid: str, action: str = "typing_on"):
    try:
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        payload = {"recipient": {"id": recipient_psid}, "sender_action": action}
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass  # Non-critical

# ==================================================
# GEMINI API
# ==================================================
@smart_retry(max_retries=3, base_delay=1.0)
def ask_gemini(sender_id: str, user_message: str) -> str:
    sentiment = detect_sentiment(user_message)
    storage.set_sentiment(sender_id, sentiment)

    history = storage.get_memory(sender_id)

    contents = []
    for msg in history[-MAX_HISTORY:]:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({
            "role": role,
            "parts": [{"text": msg["text"]}]
        })

    contents.append({
        "role": "user",
        "parts": [{"text": user_message}]
    })

    system_instruction = get_persona_with_sentiment(sentiment)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"

    payload = {
        "system_instruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 500,
            "topP": 0.95
        }
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        result = response.json()

        if "error" in result:
            logger.error(f"[GEMINI ERROR] {result['error']}")
            return "⚠️ Technical issue. Try again later."

        reply = result["candidates"][0]["content"]["parts"][0]["text"].strip()

        storage.add_to_memory(sender_id, "user", user_message)
        storage.add_to_memory(sender_id, "assistant", reply)

        return reply

    except Exception as e:
        logger.error(f"[GEMINI REQUEST FAILED] {e}")
        return "⚠️ I'm having trouble connecting to AI service."


def generate_professional_post() -> Optional[str]:
    topic = random.choice(PROFESSIONAL_TOPICS)
    logger.info(f"[AUTO-POST] Generating post about: {topic}")
    
    prompt = f"""Write a professional 5-paragraph Facebook post about: {topic}
    ... (rest of your prompt) ...
    """
    
    # The URL uses the GEMINI_MODEL variable defined above
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 900,
            "topP": 0.95
        }
    }
    # ... rest of the function
    
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, json=data, headers=headers, timeout=30)
    result = response.json()
    
    if "error" in result:
        logger.error(f"[GEMINI ERROR] {result['error'].get('message')}")
        return "🤖 Technical hiccup. Please try again!"
    
    if "candidates" not in result or not result["candidates"]:
        return "😅 Can you repeat that?"
    
    reply = result["candidates"][0]["content"]["parts"][0]["text"].strip()
    
    storage.add_to_memory(sender_id, "user", user_message)
    storage.add_to_memory(sender_id, "assistant", reply)
    
    return reply

# ==================================================
# SEND MESSENGER
# ==================================================
def send_messenger(recipient_psid: str, message: str) -> bool:
    try:
        send_typing_action(recipient_psid, "typing_on")
        time_module.sleep(0.3)
        send_typing_action(recipient_psid, "typing_off")
        
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        payload = {
            "recipient": {"id": recipient_psid},
            "message": {"text": message}
        }
        
        response = requests.post(url, json=payload, timeout=30)
        result = response.json()
        
        if "error" in result:
            logger.error(f"[SEND ERROR] {result['error'].get('message')}")
            return False
        
        return True
    except Exception as e:
        logger.error(f"[SEND ERROR] {e}")
        return False

# ==================================================
# PROFESSIONAL POSTS
# ==================================================
PROFESSIONAL_TOPICS = [
    "enterprise cloud migration strategies and cost optimization",
    "AI-powered business intelligence and predictive analytics",
    "zero-trust security architecture implementation",
    "scaling startups with microservices vs monoliths",
    "data governance and compliance in African markets"
]

FALLBACK_POSTS = [
    """Most companies treat data backup as an afterthought — until it's too late. A single corrupted database can wipe out years of work.

The 3-2-1 backup rule remains the gold standard: 3 copies of your data, on 2 different types of media, with 1 copy stored offsite.

Start today: identify your most critical data, implement automated daily backups, and test your restore process monthly.

Is your business data properly protected? 💾""",

    """Building scalable software isn't about choosing the right framework — it's about understanding your data flow.

We recently helped a client reduce API response time from 4 seconds to 200ms by batching database queries.

Before adding caching layers, profile your slowest endpoints. Often the fix is simpler than you think.

What's your biggest performance bottleneck? 🔍"""
]

@smart_retry(max_retries=2, base_delay=2.0)
def generate_professional_post() -> Optional[str]:
    topic = random.choice(PROFESSIONAL_TOPICS)
    logger.info(f"[AUTO-POST] Generating post about: {topic}")
    
    prompt = f"""Write a professional 5-paragraph Facebook post about: {topic}

Structure:
Paragraph 1: Hook - state the problem
Paragraph 2: Why it matters for businesses
Paragraph 3: Key insight or approach
Paragraph 4: Practical example
Paragraph 5: Call to action or question

Keep it professional, 300-500 words. No hashtags. Include 2-3 emojis total."""
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 900,
            "topP": 0.95
        }
    }
    
    response = requests.post(url, json=data, timeout=45)
    result = response.json()
    
    if "candidates" in result and result["candidates"]:
        post_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        paragraphs = [p for p in post_text.split('\n\n') if p.strip()]
        
        if len(paragraphs) >= 4 and len(post_text.split()) >= 200:
            return post_text
    
    return None

def post_to_page(message: str) -> bool:
    try:
        url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/feed"
        payload = {"message": message, "access_token": PAGE_ACCESS_TOKEN}
        
        response = requests.post(url, data=payload, timeout=30)
        result = response.json()
        
        if "id" in result:
            logger.info(f"[POST] ✅ Published! Post ID: {result['id']}")
            return True
        else:
            logger.error(f"[POST ERROR] {result.get('error', {}).get('message')}")
            return False
    except Exception as e:
        logger.error(f"[POST ERROR] {e}")
        return False

def four_hour_auto_post():
    logger.info("[AUTO-POST] Running 4-hour scheduled post...")
    
    post_content = generate_professional_post()
    
    if not post_content or len(post_content.split()) < 200:
        post_content = random.choice(FALLBACK_POSTS)
    
    success = post_to_page(post_content)
    if success:
        storage.set_last_post_time(datetime.now())
        logger.info("[AUTO-POST] ✅ Published successfully!")

# ==================================================
# SPAM DETECTION
# ==================================================
def is_spam(text: str) -> bool:
    if len(text) > 1000:
        return True
    
    spam_patterns = ["click here", "free money", "crypto", "bitcoin", "lottery", "http://", "https://"]
    text_lower = text.lower()
    
    if any(pattern in text_lower for pattern in spam_patterns):
        return True
    
    return False

# ==================================================
# OWNER COMMANDS
# ==================================================
def handle_owner_command(sender_id: str, command: str) -> Tuple[bool, Optional[str]]:
    if command == "!stop":
        storage.set_paused(sender_id, True)
        return True, "🤖 Bot paused. Type !start to resume."
    
    elif command == "!start":
        storage.set_paused(sender_id, False)
        return True, "🤖 Bot resumed."
    
    elif command == "!post":
        four_hour_auto_post()
        return True, "📝 Publishing post now. Check your page!"
    
    elif command == "!status":
        stats = storage.get_stats()
        last_post = storage.get_last_post_time()
        status_msg = (
            f"📊 Bot Status\n"
            f"• Active chats: {stats['active_conversations']}\n"
            f"• Unique users: {stats['unique_users']}\n"
            f"• Last post: {last_post.strftime('%Y-%m-%d %H:%M') if last_post else 'Never'}\n"
            f"• Model: {GEMINI_MODEL}"
        )
        return True, status_msg
    
    elif command == "!reset":
        storage.chat_memory.pop(sender_id, None)
        return True, "🗑 Memory cleared!"
    
    return False, None

# ==================================================
# WEBHOOK ENDPOINTS
# ==================================================
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    
    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("[WEBHOOK] ✅ Verified")
        return challenge, 200
    
    return "Verification failed", 403

@app.route("/webhook", methods=["POST"])
def receive_message():
    if APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not signature:
            return "Invalid signature", 403
        
        expected = hmac.new(APP_SECRET.encode(), request.data, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, f"sha256={expected}"):
            return "Invalid signature", 403
    
    data = request.get_json()
    if not data:
        return jsonify({"status": "ok"}), 200
    
    try:
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                sender_id = event["sender"]["id"]
                
                if "message" not in event:
                    continue
                
                message = event.get("message", {})
                if "text" not in message:
                    continue
                
                message_id = message.get("mid", "")
                if message_id and storage.is_duplicate(message_id):
                    continue
                
                text = message["text"].strip()
                if not text:
                    continue
                
                logger.info(f"[MESSAGE] {sender_id[:10]}...: {text[:100]}")
                
                if is_spam(text):
                    send_messenger(sender_id, "⚠️ Message not delivered.")
                    continue
                
                if storage.check_rate_limit(sender_id):
                    send_messenger(sender_id, "⏳ Please slow down.")
                    continue
                
                if sender_id == OWNER_PSID:
                    handled, response = handle_owner_command(sender_id, text.lower())
                    if handled:
                        if response:
                            send_messenger(sender_id, response)
                        continue
                
                if storage.is_paused(sender_id):
                    continue
                
                reply = ask_gemini(sender_id, text)
                send_messenger(sender_id, reply)
                
    except Exception as e:
        logger.error(f"[WEBHOOK ERROR] {e}")
    
    return jsonify({"status": "success"}), 200

# ==================================================
# SCHEDULER
# ==================================================
def scheduler_loop():
    time_module.sleep(120)
    logger.info("[SCHEDULER] Started")
    
    while True:
        try:
            now = datetime.now()
            last_post = storage.get_last_post_time()
            
            if last_post is None or (now - last_post).total_seconds() >= 14400:
                logger.info("[SCHEDULER] Triggering 4-hour post")
                four_hour_auto_post()
            
            time_module.sleep(60)
        except Exception as e:
            logger.error(f"[SCHEDULER ERROR] {e}")
            time_module.sleep(300)

scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
scheduler_thread.start()

# ==================================================
# HEALTH ENDPOINTS
# ==================================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "service": "Kanyoza Systems Bot",
        "version": "4.0",
        "model": GEMINI_MODEL,
        "stats": storage.get_stats()
    })

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

# ==================================================
# MAIN
# ==================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"[STARTUP] Starting server on port {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)

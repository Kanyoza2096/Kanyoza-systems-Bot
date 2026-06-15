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
# LOGGING
# ==================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

logger.info("=" * 60)
logger.info("KANYOZA SYSTEMS BOT v4.0 - Gemini 2.5 Flash")

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

storage = ThreadSafeStorage()

# ==================================================
# PERSONA & FALLBACKS
# ==================================================
MADA_PERSONA_BASE = """
You are Madalitso, a professional yet witty software engineer from Malawi.
You represent Kanyoza Systems — a respected tech company.

RULES:
1. PRIMARY LANGUAGE: English always (professional tech context)
2. Chichewa allowed only if someone send message in chichewa and only for: "Moni", "Zikomo", "Bho" — never full sentences
3. Keep replies SHORT (1-2 sentences for casual, 3-4 for technical questions)
4. Be friendly, knowledgeable, slightly sarcastic but never rude
5. If technical question: Give clear, accurate answer
6. If unsure: "That data is currently unavailable. Check back later!"
7. Never sound robotic or like customer service
"""

PROFESSIONAL_TOPICS = [
    "artificial intelligence and automation for businesses",
    "custom software development and cloud architecture",
    "mobile application development trends in Africa",
    "cybersecurity strategies and protecting corporate data",
    "why systems integration scales modern businesses",
    "the future of web applications and UX design",
    "data-driven decision making and business analytics"
]

FALLBACK_TEMPLATES = [
    "🔒 [Security Tip] {idea} — Protect your business digital assets before vulnerability becomes a threat. #CyberSecurity #KanyozaSystems",
    "💡 [System Insight] {idea} — Scalable system architecture starts with clean engineering choices. #CloudComputing #TechInfrastructure",
    "🛠️ [Engineering Lesson] {idea} — Code maintenance costs more than initial design. Build it right the first time. #SoftwareEngineering #TechTips",
    "🚀 [Business Strategy] {idea} — Modernizing your technical workflow is the fastest way to reduce overhead and scale operations. #BizTech #Innovation",
    "🤖 [AI Innovation] {idea} — Integrating smart automation loops into your current pipelines saves hours of manual overhead. #ArtificialIntelligence #Kanyoza",
    "💻 [Dev Tip] {idea} — Write self-documenting code and write robust tests. Future you will thank you. #CleanCode #DeveloperTips"
]

BACKUP_IDEAS = [
    "Isolate your database clusters inside private networks.",
    "Ensure all legacy applications employ stateless design pipelines.",
    "Regularly audit deployment containers for unpatched dependency exploits.",
    "Decouple monolith architectures using async event-driven brokers.",
    "Implement zero-trust security architecture across API access grids."
]

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
                        logger.warning(f"[RETRY] Attempt {attempt+1}/{max_retries} failed, retrying in {delay:.1f}s")
                        time_module.sleep(delay)
            raise last_exception
        return wrapper
    return decorator

# ==================================================
# API CALLS - GEMINI & FACEBOOK
# ==================================================
@smart_retry(max_retries=3, base_delay=1.5)
# ==================================================
# API CALLS - GEMINI & FACEBOOK (OPTIMIZED & BULLETPROOF)
# ==================================================
def ask_gemini(sender_id: str, user_message: str, is_cron: bool = False) -> str:
    """Queries Google Gemini 2.5 Flash Endpoint securely with safe error tracking"""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
        
        if is_cron:
            prompt = user_message
        else:
            sentiment = storage.get_sentiment(sender_id)
            persona = get_persona_with_sentiment(sentiment)
            history = storage.get_memory(sender_id)
            context_lines = [f"{'Friend' if m['role']=='user' else 'You'}: {m['text']}" for m in history[-10:]]
            context = "\n".join(context_lines)
            prompt = f"{persona}\n\nRecent conversation:\n{context}\n\nFriend: {user_message}\nYou (Madalitso):"
        
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.85 if is_cron else 0.7,
                "maxOutputTokens": 900 if is_cron else 200,
                "topP": 0.95
            }
        }
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=data, headers=headers, timeout=30)
        result = response.json()
        
        # 1. Handle API Error Payloads Explicitly Without Raising Triggers
        if "error" in result:
            error = result["error"]
            status = error.get("status", "")
            logger.error(f"[GEMINI ERROR] Status: {status} | Message: {error.get('message')}")
            
            
        # 2. Safe Parsing Variant to Prevent IndexError Crashing
        candidates = result.get("candidates", [])
        if not candidates:
            logger.error(f"[GEMINI ERROR] Empty payload response candidates grid: {result}")
            return "Zinthu zili down pakali pano, ticheza kenako 😄"
            
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts or "text" not in parts[0]:
            logger.error(f"[GEMINI ERROR] No readable text inside generation frame: {result}")
            return "Zinthu zili down pakali pano, ticheza kenako 😄"
            
        reply = parts[0]["text"].strip()
        
        if not is_cron:
            storage.add_to_memory(sender_id, "user", user_message)
            storage.add_to_memory(sender_id, "assistant", reply)
        
        return reply
    except Exception as e:
        logger.error(f"Failed to query Gemini: {e}")
        return "Busy right now, just leave the message!!"

@smart_retry(max_retries=3, base_delay=1.0)
def send_messenger(recipient_psid: str, message: str):
    """Sends outbound text message blocks back through Page Webhook Channels"""
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_psid}, "message": {"text": message}}
    response = requests.post(url, json=payload, timeout=30)
    if response.status_code != 200:
        logger.error(f"[MESSENGER SEND ERROR] {response.json()}")

@smart_retry(max_retries=3, base_delay=2.0)
def post_to_page(message: str) -> bool:
    """Publishes structural educational updates to the Page's public feed"""
    url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/feed"
    payload = {"message": message, "access_token": PAGE_ACCESS_TOKEN}
    logger.info(f"[POST] Publishing directly to target Page feed ID: {PAGE_ID}")
    response = requests.post(url, data=payload, timeout=30)
    result = response.json()
    if "id" in result:
        logger.info(f"[POST] ✅ Success! Post ID created: {result['id']}")
        storage.set_last_post_time(datetime.now())
        return True
    logger.error(f"[POST ERROR FEED] {result.get('error', {}).get('message')}")
    return False
                         


def send_typing_on(recipient_psid: str):
    """Triggers the 'typing...' bubble interface for aesthetic UX continuity"""
    try:
        # FIXED: Correct URL with https://
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        payload = {"recipient": {"id": recipient_psid}, "sender_action": "typing_on"}
        requests.post(url, json=payload, timeout=5)
    except:
        pass

# ==================================================
# 🎉 AUTOMATED 4-HOUR CRON THREAD MANAGER
# ==================================================
# ==================================================
# PROFESSIONAL POSTS - FIXED VERSION
# ==================================================

@smart_retry(max_retries=2, base_delay=2.0)
def generate_professional_post() -> Optional[str]:
    """Generate a professional 5-paragraph post using Gemini"""
    topic = random.choice(PROFESSIONAL_TOPICS)
    logger.info(f"[AUTO-POST] Generating post about: {topic}")
    
    prompt = f"""Write a professional 5-paragraph Facebook post about: {topic}

Paragraph 1: Hook - state the problem
Paragraph 2: Why it matters for businesses
Paragraph 3: Key insight or approach
Paragraph 4: Practical example
Paragraph 5: Call to action or question

Keep it professional, 300-500 words. No hashtags. Include 2-3 emojis."""
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 900,
            "topP": 0.95
        }
    }
    
    try:
        response = requests.post(url, json=data, timeout=45)
        result = response.json()
        
        # FIXED: Check candidates exist before using them
        if result.get("candidates"):
            post_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            word_count = len(post_text.split())
            logger.info(f"[AUTO-POST] Generated {word_count} words")
            return post_text
        else:
            error_msg = result.get("error", {}).get("message", "Unknown error")
            logger.error(f"[AUTO-POST] API error: {error_msg}")
            return None
            
    except Exception as e:
        logger.error(f"[AUTO-POST] Exception: {e}")
        return None

def four_hour_auto_post():
    """Generate and publish post every 4 hours with fallback"""
    logger.info("[AUTO-POST] Running 4-hour scheduled post...")
    
    # Try to generate with Gemini
    post_content = generate_professional_post()
    
    # Check if content is valid
    if not post_content or len(post_content.split()) < 150:
        logger.warning("[AUTO-POST] Gemini failed or content too short, using fallback")
        backup_idea = random.choice(BACKUP_IDEAS)
        post_content = random.choice(FALLBACK_TEMPLATES).format(idea=backup_idea)
    
    # Publish to Facebook
    success = post_to_page(post_content)
    if success:
        storage.set_last_post_time(datetime.now())
        logger.info("[AUTO-POST] ✅ Published successfully!")
    else:
        logger.error("[AUTO-POST] ❌ Failed to publish")

# ==================================================
# SCHEDULER LOOP (Calls four_hour_auto_post every 4 hours)
# ==================================================
def scheduler_loop():
    """Background thread that runs the auto-post every 4 hours"""
    time_module.sleep(15)  # Wait 15 seconds on startup
    logger.info("[SCHEDULER] Auto-post scheduler started")
    
    while True:
        try:
            four_hour_auto_post()  # ← Calls your function
            logger.info("[SCHEDULER] Sleeping for 4 hours...")
            time_module.sleep(14400)  # 4 hours in seconds
        except Exception as e:
            logger.error(f"[SCHEDULER ERROR] {e}")
            time_module.sleep(300)  # On error, wait 5 minutes then retry

# Launch thread correctly - FIXED function name
cron_thread = threading.Thread(target=scheduler_loop, daemon=True)
cron_thread.start()
logger.info("[STARTUP] Scheduler thread started")

# ==================================================
# WEBHOOK WEB ROUTES (FLASK HANDLERS)
# ==================================================
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Verification token mismatch", 403

@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    
    try:
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                sender_id = event["sender"]["id"]
                message_id = event.get("message", {}).get("mid")
                
                if message_id and storage.is_duplicate(message_id):
                    continue
                
                if "message" in event and "text" in event["message"]:
                    text = event["message"]["text"].strip()
                    logger.info(f"[INBOUND] From: {sender_id} - text: {text}")
                    
                    if storage.check_rate_limit(sender_id):
                        send_messenger(sender_id, "⏳ You are sending too many requests. Please slow down.")
                        continue
                    
                    # Admin manual commands
                    if sender_id == OWNER_PSID:
                        if text.lower() == "!stop":
                            storage.set_paused(sender_id, True)
                            send_messenger(sender_id, "🤖 Bot paused for 30 minutes. Manual mode active.")
                            continue
                        elif text.lower() == "!start":
                            storage.set_paused(sender_id, False)
                            send_messenger(sender_id, "🤖 Bot resumed. Madalitso is active.")
                            continue
                        elif text.lower() == "!post":
                            send_messenger(sender_id, "⚙️ Triggering manual 4-hour background tech post immediately...")
                            threading.Thread(target=generate_and_publish_tech_post).start()
                            continue
                    
                    if storage.is_paused(sender_id):
                        continue
                    
                    # Dynamic user tracking configuration
                    sentiment = detect_sentiment(text)
                    storage.set_sentiment(sender_id, sentiment)
                    
                    # Generate dynamic chat reply block
                    send_typing_on(sender_id)
                    reply = ask_gemini(sender_id, text, is_cron=False)
                    send_messenger(sender_id, reply)
                    
    except Exception as e:
        logger.error(f"[SYSTEM ROUTE EXCEPTION] {e}")
    
    return "EVENT_RECEIVED", 200

@app.route("/status", methods=["GET"])
def system_status():
    """Debug route to instantly view operational parameters"""
    stats = storage.get_stats()
    stats.update({
        "status": "online",
        "version": "4.0.0",
        "gemini_model": GEMINI_MODEL,
        "last_post_timestamp": str(storage.get_last_post_time())
    })
    return jsonify(stats), 200

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "service": "Kanyoza Systems Bot",
        "version": "4.0"
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

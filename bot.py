"""
bot.py — Kanyoza Systems Messenger Bot v4.0
Gemini 2.5 Flash | 4-Hour Professional Posts | AI Chat | Smart Features
Deploy to Render.com

Features:
- AI Chat with Gemini 2.5 Flash (2M context window)
- Auto 4-Hour Professional Posts (5-7 paragraphs)
- Typing indicators & Quick Reply buttons
- Sentiment-aware responses
- Smart retry with exponential backoff
- Rate limiting (10 msg/min) & Spam detection
- Owner commands (!stop, !start, !post, !status, !reset, !broadcast)
- Thread-safe storage & Idempotent webhook handling
- Health checks & monitoring endpoints
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
GEMINI_MODEL = "gemini-2.5-flash"  # Correct model name
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
PAGE_ID = os.getenv("PAGE_ID", "1237042419481977")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "my_secret_token_123")
OWNER_PSID = os.getenv("OWNER_PSID")
APP_SECRET = os.getenv("APP_SECRET", "")

# Rate limiting: 10 messages per minute per user
RATE_LIMIT = 10
RATE_WINDOW_SECONDS = 60

# Memory: Keep last 30 messages (Gemini 2.5 Flash handles 2M context easily)
MAX_HISTORY = 30

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
logger.info(f"Gemini Key: {'✅ SET' if GEMINI_KEY else '❌ MISSING'}")
logger.info(f"Page Token: {'✅ SET' else '❌ MISSING'}")
logger.info(f"Page ID: {PAGE_ID}")
logger.info(f"Owner PSID: {'✅ SET' if OWNER_PSID else '❌ MISSING'}")
logger.info(f"Model: {GEMINI_MODEL}")
logger.info("=" * 60)

# ==================================================
# THREAD-SAFE STORAGE
# ==================================================
class ThreadSafeStorage:
    """Thread-safe wrapper for all shared state"""
    
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
            
            # Trim if needed
            if len(self.chat_memory[sender_id]) > MAX_HISTORY + 10:
                self.chat_memory[sender_id] = self.chat_memory[sender_id][-MAX_HISTORY:]
    
    def is_duplicate(self, message_id: str) -> bool:
        with self._lock:
            if message_id in self.processed_messages:
                # Clean up old entries (older than 1 hour)
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
            
            # Clean old entries
            self.request_tracker[sender_id] = [
                t for t in self.request_tracker[sender_id] 
                if now - t < timedelta(seconds=RATE_WINDOW_SECONDS)
            ]
            
            if len(self.request_tracker[sender_id]) >= RATE_LIMIT:
                logger.warning(f"[RATE LIMIT] Blocked {sender_id[:10]}...")
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
                # Auto-resume after 30 minutes
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
                "processed_messages_24h": len(self.processed_messages),
                "unique_users": len(self.chat_memory)
            }
    
    def get_recent_users(self, limit: int = 50) -> List[str]:
        with self._lock:
            return list(self.chat_memory.keys())[:limit]

storage = ThreadSafeStorage()

# ==================================================
# PERSONA (Enhanced with sentiment awareness)
# ==================================================
MADA_PERSONA_BASE = """
You are Madalitso, a professional yet witty software engineer from Malawi.
You represent Kanyoza Systems — a respected tech company.

CORE RULES:
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
        return MADA_PERSONA_BASE + """
\nSPECIAL INSTRUCTION: User seems frustrated or angry. 
- Apologize briefly if appropriate
- Stay calm and extra patient
- Offer specific help
- Keep tone warm and non-defensive"""
    elif sentiment == "enthusiastic":
        return MADA_PERSONA_BASE + """
\nSPECIAL INSTRUCTION: User is excited or enthusiastic.
- Match their positive energy
- Be encouraging
- Share excitement about tech topics"""
    return MADA_PERSONA_BASE

# ==================================================
# SENTIMENT DETECTION
# ==================================================
def detect_sentiment(text: str) -> str:
    """Detect user sentiment from message text"""
    text_lower = text.lower()
    
    angry_patterns = [
        "useless", "stupid", "hate", "angry", "frustrated", 
        "terrible", "worst", "awful", "bad bot", "useless bot",
        "not working", "broken"
    ]
    
    enthusiastic_patterns = [
        "love", "awesome", "great", "excellent", "amazing", 
        "best", "fantastic", "brilliant", "perfect", "wonderful"
    ]
    
    if any(word in text_lower for word in angry_patterns):
        return "angry"
    elif any(word in text_lower for word in enthusiastic_patterns):
        return "enthusiastic"
    return "neutral"

# ==================================================
# SMART RETRY DECORATOR
# ==================================================
def smart_retry(max_retries: int = 3, base_delay: float = 1.0):
    """Exponential backoff retry decorator for API calls"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.Timeout as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                        logger.warning(f"[RETRY] {func.__name__} timeout, retry {attempt+1}/{max_retries} in {delay:.1f}s")
                        time_module.sleep(delay)
                except requests.exceptions.RequestException as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"[RETRY] {func.__name__} failed, retry {attempt+1}/{max_retries} in {delay:.1f}s: {e}")
                        time_module.sleep(delay)
            logger.error(f"[RETRY] {func.__name__} failed after {max_retries} attempts")
            raise last_exception
        return wrapper
    return decorator

# ==================================================
# TYPING INDICATOR
# ==================================================
def send_typing_action(recipient_psid: str, action: str = "typing_on"):
    """Send typing indicator to Facebook Messenger"""
    try:
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        payload = {"recipient": {"id": recipient_psid}, "sender_action": action}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.debug(f"Typing indicator failed (non-critical): {e}")

# ==================================================
# QUICK REPLY BUTTONS
# ==================================================
def send_with_quick_replies(recipient_psid: str, message: str, replies: List[Tuple[str, str]]) -> bool:
    """Send message with quick reply buttons"""
    try:
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        quick_replies = [
            {"content_type": "text", "title": title, "payload": payload}
            for title, payload in replies
        ]
        payload = {
            "recipient": {"id": recipient_psid},
            "message": {
                "text": message,
                "quick_replies": quick_replies
            }
        }
        response = requests.post(url, json=payload, timeout=30)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Quick reply send error: {e}")
        return False

# ==================================================
# GEMINI 2.5 FLASH API
# ==================================================
@smart_retry(max_retries=3, base_delay=1.0)
def ask_gemini(sender_id: str, user_message: str) -> str:
    """Send message to Gemini 2.5 Flash, return AI reply with context"""
    
    # Detect and store sentiment
    sentiment = detect_sentiment(user_message)
    storage.set_sentiment(sender_id, sentiment)
    
    # Build conversation context from memory
    history = storage.get_memory(sender_id)
    
    # Format conversation for Gemini's multi-turn format
    contents = []
    for msg in history[-MAX_HISTORY:]:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["text"]}]})
    
    # Add current message
    contents.append({"role": "user", "parts": [{"text": user_message}]})
    
    # Prepare system instruction with sentiment
    system_instruction = get_persona_with_sentiment(sentiment)
    
    # Gemini 2.5 Flash API endpoint
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    
    data = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 500,
            "topP": 0.95,
            "topK": 40
        }
    }
    
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, json=data, headers=headers, timeout=30)
    result = response.json()
    
    # Error handling with user-friendly messages
    if "error" in result:
        error = result["error"]
        logger.error(f"[GEMINI ERROR] {error.get('code')}: {error.get('message')}")
        
        if error.get("status") == "RESOURCE_EXHAUSTED":
            return "⏳ Busy moment! Try again in a few seconds."
        elif error.get("status") == "INVALID_ARGUMENT":
            return "⚠️ Configuration issue. Our team has been notified."
        elif error.get("status") == "PERMISSION_DENIED":
            return "⚠️ API permission issue. Please check your key."
        else:
            return "🤖 Technical hiccup. Give me a moment and try again!"
    
    if "candidates" not in result or not result["candidates"]:
        logger.error(f"Empty Gemini response: {result}")
        return "😅 I lost my thought. Can you repeat that?"
    
    reply = result["candidates"][0]["content"]["parts"][0]["text"].strip()
    
    # Store conversation in memory
    storage.add_to_memory(sender_id, "user", user_message)
    storage.add_to_memory(sender_id, "assistant", reply)
    
    logger.info(f"[GEMINI] Reply: {reply[:100]}..." if len(reply) > 100 else f"[GEMINI] Reply: {reply}")
    return reply

# ==================================================
# FACEBOOK MESSENGER SEND
# ==================================================
def send_messenger(recipient_psid: str, message: str) -> bool:
    """Send message via Facebook Messenger API with typing indicator"""
    try:
        # Show typing indicator for natural feel
        send_typing_action(recipient_psid, "typing_on")
        time_module.sleep(0.3)  # Brief pause for realism
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
        
        logger.info(f"[SEND] Success to {recipient_psid[:10]}...")
        return True
        
    except Exception as e:
        logger.error(f"[SEND ERROR] {e}")
        return False

# ==================================================
# PROFESSIONAL 4-HOUR AUTO POST
# ==================================================
PROFESSIONAL_TOPICS = [
    "enterprise cloud migration strategies and cost optimization",
    "AI-powered business intelligence and predictive analytics",
    "zero-trust security architecture implementation",
    "scaling startups with microservices vs monoliths",
    "data governance and compliance in African markets",
    "edge computing for low-latency applications",
    "DevOps maturity models and continuous delivery",
    "RESTful API design best practices for enterprise",
    "serverless architecture: pros, cons, and use cases",
    "database sharding strategies for high-growth platforms",
    "mobile-first architecture for African markets",
    "cybersecurity incident response planning",
    "technical debt management in agile teams",
    "CI/CD pipeline optimization for faster delivery",
    "legacy system modernization without business disruption",
    "disaster recovery and business continuity planning",
    "blockchain for supply chain transparency",
    "IoT data processing at scale",
    "Fintech integration in emerging markets",
    "green software engineering and sustainable computing"
]

# High-quality fallback posts (ensures content even if Gemini fails)
FALLBACK_POSTS = [
    """Most companies treat data backup as an afterthought — until it's too late. A single corrupted database or accidental deletion can wipe out years of work.

The 3-2-1 backup rule remains the gold standard: 3 copies of your data, on 2 different types of media, with 1 copy stored offsite. Cloud backups now cost less than MWK 10,000 per month for most small businesses.

Yet we still see clients running their entire operation on a single laptop with no backup strategy. When that hard drive fails — and it will — the cost of recovery often exceeds the cost of prevention by 100x.

Start today: identify your most critical data (customer records, financials, code), implement automated daily backups, and test your restore process monthly. A backup you've never tested is not a backup — it's hope.

Is your business data properly protected? When did you last test a restore? 💾""",

    """Building scalable software isn't about choosing the right framework — it's about understanding your data flow. Most performance problems trace back to one root cause: chatty communication between services.

We recently helped a client reduce their API response time from 4 seconds to 200ms by doing one thing: batching database queries. Their code was making 50 separate calls when one would do. This pattern repeats everywhere.

Before adding caching layers or buying bigger servers, profile your slowest endpoints. Look for N+1 queries, redundant API calls, and synchronous operations that could be parallelized. Often, the fix is simpler than you think.

What's your biggest performance bottleneck right now? 🔍""",

    """The gap between a good developer and a great one isn't technical skill — it's understanding business value. I've seen brilliant architects build systems no one needed, and average developers deliver features that doubled revenue.

At Kanyoza Systems, we practice "outcome-driven development." Before writing a single line of code, we ask: What business metric will this improve? By how much? How will we measure success?

This simple question prevents months of wasted effort. It reveals when a "simple" feature would actually require rebuilding half the system for marginal gain. It helps stakeholders prioritize what truly matters.

Next time you're asked to build something, ask "What problem are we solving, and how will we know we've solved it?" The answer might surprise you. 🎯""",

    """Security isn't a product you buy — it's a discipline you practice. Firewalls and antivirus are necessary but not sufficient. The weakest link in any system is always human.

Phishing attacks succeed because they exploit trust and urgency, not technical vulnerabilities. Your team needs regular training, simulated attacks, and a culture where reporting a mistake is rewarded, not punished.

One client reduced their phishing click rate from 32% to 4% in six months through monthly simulations and positive reinforcement. No new software — just better habits.

When was your last security training? Does your team know how to spot a suspicious link? 🔐""",

    """The best technology strategy is the one your team can actually implement. I've seen beautiful architectures fail because they required skills no one had, or tools that didn't fit the problem.

Start with boring technology that works. PostgreSQL, Redis, a simple monolith. Only introduce complexity when you have proven need: 1000+ concurrent users, multiple teams, or compliance requirements.

Microservices solve organizational problems, not technical ones. If you have three developers, you probably don't need Kubernetes. If you have thirty, you might. Scale your complexity with your team size.

What's the simplest solution that could possibly work for your current problem? Start there, then iterate. 🏗️"""
]

@smart_retry(max_retries=2, base_delay=2.0)
def generate_professional_post() -> Optional[str]:
    """Generate a high-quality 5-7 paragraph professional post using Gemini 2.5 Flash"""
    
    topic = random.choice(PROFESSIONAL_TOPICS)
    logger.info(f"[AUTO-POST] Generating post about: {topic} using {GEMINI_MODEL}")
    
    prompt = f"""You are a senior technology architect at Kanyoza Systems, a leading tech consulting firm in Malawi.
Write a THOUGHT LEADERSHIP Facebook post about: {topic}

CRITICAL FORMATTING REQUIREMENTS:
- MUST be 5-7 PARAGRAPHS (not sentences)
- Each paragraph: 2-4 sentences
- Total length: 300-500 words
- Professional but conversational tone (like a CTO sharing insights)

STRUCTURE TO FOLLOW (strict):
Paragraph 1 (Hook): State the problem or opportunity — grab attention
Paragraph 2 (Why it matters): Business impact and real-world relevance
Paragraph 3 (The insight): What experienced practitioners know
Paragraph 4 (Example/Evidence): Specific case study or data point
Paragraph 5 (Actionable advice): What readers should do differently
Paragraphs 6-7 (Optional): Deeper nuance or concluding question

STYLE RULES:
- No jargon without explanation
- Include 2-3 relevant emojis total (spread across paragraphs)
- No hashtags
- No "click here" or "contact us"
- Sound like an expert teaching, not selling
- End with a thought-provoking question

Write ONLY the post. Start directly with paragraph 1. No greetings, no explanations, no "Here is a post". Begin immediately with content."""
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.85,  # Slightly creative for engaging posts
            "maxOutputTokens": 900,  # Enough for 500+ words
            "topP": 0.95,
            "topK": 40
        }
    }
    
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, json=data, headers=headers, timeout=45)
    result = response.json()
    
    if "error" in result:
        logger.error(f"[AUTO-POST] Gemini error: {result['error'].get('message')}")
        return None
    
    if "candidates" not in result or not result["candidates"]:
        logger.error(f"[AUTO-POST] No candidates in response")
        return None
    
    post_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
    
    # Validate quality
    paragraphs = [p for p in post_text.split('\n\n') if p.strip()]
    para_count = len(paragraphs)
    word_count = len(post_text.split())
    
    logger.info(f"[AUTO-POST] Generated: {para_count} paragraphs, {word_count} words")
    
    # Quality check: need at least 4 paragraphs and 200 words
    if para_count < 4 or word_count < 200:
        logger.warning(f"[AUTO-POST] Quality low ({para_count} paras, {word_count} words)")
        return None
    
    return post_text

def post_to_page(message: str) -> bool:
    """Post content to Facebook page"""
    try:
        url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/feed"
        payload = {"message": message, "access_token": PAGE_ACCESS_TOKEN}
        
        logger.info(f"[POST] Publishing to page {PAGE_ID}...")
        response = requests.post(url, data=payload, timeout=30)
        result = response.json()
        
        if "id" in result:
            logger.info(f"[POST] ✅ Published! Post ID: {result['id']}")
            return True
        else:
            error = result.get("error", {})
            logger.error(f"[POST ERROR] {error.get('message', 'Unknown')}")
            return False
            
    except Exception as e:
        logger.error(f"[POST ERROR] {e}")
        return False

def four_hour_auto_post():
    """Generate and publish professional post every 4 hours"""
    logger.info("[AUTO-POST] 🚀 Running 4-hour scheduled post...")
    
    # Try Gemini first
    post_content = generate_professional_post()
    
    # Fallback to hardcoded posts if Gemini fails or produces low quality
    if not post_content or len(post_content.split()) < 200:
        logger.info("[AUTO-POST] Using fallback post due to quality or failure")
        post_content = random.choice(FALLBACK_POSTS)
    
    success = post_to_page(post_content)
    if success:
        storage.set_last_post_time(datetime.now())
        logger.info("[AUTO-POST] ✅ 4-hour post published successfully!")
    else:
        logger.error("[AUTO-POST] ❌ Failed to publish post")

# ==================================================
# SPAM DETECTION
# ==================================================
def is_spam(text: str) -> bool:
    """Detect and filter spam messages before AI processing"""
    text_lower = text.lower()
    
    spam_patterns = [
        "click here", "free money", "crypto", "invest now", "bitcoin",
        "lottery", "you won", "prize", "casino", "viagra", 
        "http://", "https://", "www.", ".com", ".org"  # Block links
    ]
    
    # Very long messages (likely spam or copy-paste)
    if len(text) > 1000:
        logger.warning(f"[SPAM] Blocked: message too long ({len(text)} chars)")
        return True
    
    # All caps messages (shouting)
    if text.isupper() and len(text) > 50:
        logger.warning(f"[SPAM] Blocked: all caps shouting")
        return True
    
    # Excessive punctuation
    if text.count("!") > 10 or text.count("?") > 10:
        logger.warning(f"[SPAM] Blocked: excessive punctuation")
        return True
    
    # Check spam patterns
    if any(pattern in text_lower for pattern in spam_patterns):
        logger.warning(f"[SPAM] Blocked pattern in: {text[:100]}")
        return True
    
    return False

# ==================================================
# OWNER COMMANDS
# ==================================================
def handle_owner_command(sender_id: str, command: str) -> Tuple[bool, Optional[str]]:
    """Handle owner-only commands. Returns (handled, response_message)"""
    
    if command == "!stop":
        storage.set_paused(sender_id, True)
        return True, "🤖 Bot paused. You're in manual mode. Type !start to resume."
    
    elif command == "!start":
        storage.set_paused(sender_id, False)
        return True, "🤖 Bot resumed. AI responses are active again."
    
    elif command == "!post":
        four_hour_auto_post()
        return True, "📝 Generating and publishing post now. Check your page in a few moments!"
    
    elif command == "!status":
        stats = storage.get_stats()
        last_post = storage.get_last_post_time()
        status_msg = (
            f"📊 **Bot Status**\n"
            f"• Active conversations: {stats['active_conversations']}\n"
            f"• Paused chats: {stats['paused_chats']}\n"
            f"• Unique users: {stats['unique_users']}\n"
            f"• Gemini: {'✅' if GEMINI_KEY else '❌'}\n"
            f"• Model: {GEMINI_MODEL}\n"
            f"• Last post: {last_post.strftime('%Y-%m-%d %H:%M') if last_post else 'Never'}\n"
            f"• Uptime: Live 🟢"
        )
        return True, status_msg
    
    elif command == "!reset":
        # Clear memory for this user only
        storage.chat_memory.pop(sender_id, None)
        storage.user_sentiment.pop(sender_id, None)
        return True, "🗑 Your conversation memory has been cleared! Fresh start."
    
    elif command.startswith("!broadcast "):
        message = command[10:].strip()
        if not message:
            return True, "Usage: !broadcast <message>"
        
        # Get recent users (limit to 50 for safety)
        recent_users = storage.get_recent_users(limit=50)
        sent_count = 0
        
        for user_id in recent_users:
            if send_messenger(user_id, f"📢 **Kanyoza Systems Update**\n\n{message}"):
                sent_count += 1
            time_module.sleep(0.3)  # Avoid rate limits
        
        return True, f"📢 Broadcast sent to {sent_count} users."
    
    elif command == "!help":
        help_msg = (
            "🤖 **Madalitso Bot Commands**\n\n"
            "`!stop` - Pause AI responses\n"
            "`!start` - Resume AI responses\n"
            "`!post` - Manually trigger a page post\n"
            "`!status` - Show bot status\n"
            "`!reset` - Clear your conversation memory\n"
            "`!broadcast <msg>` - Send to all users (owner only)\n"
            "`!help` - Show this message"
        )
        return True, help_msg
    
    return False, None

# ==================================================
# WEBHOOK ENDPOINTS
# ==================================================
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Facebook webhook verification endpoint"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    
    logger.info(f"[WEBHOOK] Verification attempt - Mode: {mode}")
    
    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("[WEBHOOK] ✅ Verified successfully")
        return challenge, 200
    
    logger.warning(f"[WEBHOOK] ❌ Verification failed")
    return "Verification failed", 403

@app.route("/webhook", methods=["POST"])
def receive_message():
    """Receive and process Facebook messages"""
    
    # Verify signature if APP_SECRET is configured
    if APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not signature:
            logger.warning("[WEBHOOK] Missing signature")
            return "Invalid signature", 403
        
        expected = hmac.new(
            APP_SECRET.encode(),
            request.data,
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, f"sha256={expected}"):
            logger.warning("[WEBHOOK] Invalid signature")
            return "Invalid signature", 403
    
    data = request.get_json()
    
    if not data:
        return jsonify({"status": "ok"}), 200
    
    try:
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                sender_id = event["sender"]["id"]
                
                # Skip non-message events (deliveries, read receipts)
                if "message" not in event:
                    continue
                
                message = event.get("message", {})
                
                # Skip non-text messages (images, stickers, etc.)
                if "text" not in message:
                    logger.info(f"[MESSAGE] Non-text message from {sender_id[:10]}... (ignored)")
                    continue
                
                # Idempotency check (prevent duplicate processing)
                message_id = message.get("mid", "")
                if message_id and storage.is_duplicate(message_id):
                    logger.info(f"[IDEMPOTENT] Skipping duplicate message {message_id}")
                    continue
                
                text = message["text"].strip()
                
                # Skip empty messages
                if not text:
                    continue
                
                logger.info(f"[MESSAGE] From {sender_id[:10]}...: {text[:100]}")
                
                # Spam detection
                if is_spam(text):
                    send_messenger(sender_id, "⚠️ Message not delivered. Please keep conversations professional.")
                    continue
                
                # Rate limiting
                if storage.check_rate_limit(sender_id):
                    send_messenger(sender_id, "⏳ Please slow down. You're sending messages too quickly.")
                    continue
                
                # Owner commands
                if sender_id == OWNER_PSID:
                    handled, response = handle_owner_command(sender_id, text.lower())
                    if handled:
                        if response:
                            send_messenger(sender_id, response)
                        continue
                
                # Check if bot is paused for this user
                if storage.is_paused(sender_id):
                    logger.info(f"[PAUSED] Bot paused for {sender_id[:10]}...")
                    continue
                
                # Get AI response (typing indicator handled inside send_messenger)
                reply = ask_gemini(sender_id, text)
                send_messenger(sender_id, reply)
                
                # For engaged users, occasionally show quick reply options
                if len(storage.get_memory(sender_id)) > 10 and random.random() < 0.15:
                    quick_replies = [
                        ("📊 Status", "STATUS"),
                        ("🧹 Reset", "RESET"),
                        ("❓ Help", "HELP")
                    ]
                    send_with_quick_replies(sender_id, "Quick actions:", quick_replies)
                
    except Exception as e:
        logger.error(f"[WEBHOOK ERROR] {type(e).__name__}: {e}")
    
    return jsonify({"status": "success"}), 200

# ==================================================
# 4-HOUR SCHEDULER (Background Thread)
# ==================================================
def scheduler_loop():
    """Background thread that posts every 4 hours"""
    # Wait 2 minutes on startup to ensure everything is loaded
    time_module.sleep(120)
    logger.info("[SCHEDULER] 🚀 4-hour auto-post scheduler started")
    
    while True:
        try:
            now = datetime.now()
            last_post = storage.get_last_post_time()
            
            # Post every 4 hours (14400 seconds)
            if last_post is None or (now - last_post).total_seconds() >= 14400:
                logger.info("[SCHEDULER] ⏰ Triggering 4-hour auto-post")
                four_hour_auto_post()
            
            # Sleep 1 minute then check again
            time_module.sleep(60)
            
        except Exception as e:
            logger.error(f"[SCHEDULER ERROR] {e}")
            time_module.sleep(300)  # Wait 5 minutes on error

# Start scheduler thread
scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
scheduler_thread.start()
logger.info("[STARTUP] Scheduler thread started")

# ==================================================
# HEALTH & MONITORING ENDPOINTS
# ==================================================
@app.route("/", methods=["GET"])
def home():
    """Root endpoint with bot information"""
    stats = storage.get_stats()
    return jsonify({
        "status": "online",
        "service": "Kanyoza Systems Messenger Bot",
        "version": "4.0.0",
        "model": GEMINI_MODEL,
        "features": [
            "AI Chat (Gemini 2.5 Flash)",
            "4-Hour Professional Auto-Posts (5-7 paragraphs)",
            "Smart Sentiment Detection",
            "Quick Reply Buttons",
            "Spam Protection",
            "Rate Limiting (10 msg/min)",
            "Owner Commands",
            "Idempotent Processing",
            "Thread-Safe Storage"
        ],
        "stats": stats,
        "config": {
            "gemini_key": "✅" if GEMINI_KEY else "❌",
            "page_token": "✅" if PAGE_ACCESS_TOKEN else "❌",
            "owner_configured": "✅" if OWNER_PSID else "❌"
        }
    })

@app.route("/health", methods=["GET"])
def health():
    """Simple health check for Render.com"""
    return "OK", 200

@app.route("/trigger-post", methods=["POST"])
def trigger_post():
    """Manually trigger a 4-hour post (protected by admin token)"""
    auth_token = request.headers.get("X-Auth-Token")
    admin_token = os.getenv("ADMIN_TOKEN", VERIFY_TOKEN)
    
    if auth_token != admin_token:
        return jsonify({"error": "Unauthorized"}), 401
    
    four_hour_auto_post()
    return jsonify({"status": "Post triggered successfully", "timestamp": datetime.now().isoformat()}), 200

@app.route("/stats", methods=["GET"])
def get_stats():
    """Get detailed bot statistics (protected)"""
    auth_token = request.headers.get("X-Auth-Token")
    admin_token = os.getenv("ADMIN_TOKEN", VERIFY_TOKEN)
    
    if auth_token != admin_token:
        return jsonify({"error": "Unauthorized"}), 401
    
    stats = storage.get_stats()
    return jsonify(stats), 200

# ==================================================
# MAIN ENTRY POINT
# ==================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"[STARTUP] 🚀 Starting server on port {port}")
    logger.info(f"[STARTUP] Model: {GEMINI_MODEL}")
    logger.info("[STARTUP] Features active: AI Chat, 4-Hour Posts (5-7 paragraphs), Sentiment, Quick Replies")
    logger.info("[STARTUP] Ready to receive webhooks")
    app.run(host="0.0.0.0", port=port, threaded=True)
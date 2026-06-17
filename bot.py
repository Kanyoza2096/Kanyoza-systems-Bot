"""
bot.py — Kanyoza Systems Messenger Bot v5.0
Human-Like AI Chat | Premium Auto-Posting | Persistent Memory
"""

import os
import json
import logging
import random
import hashlib
import hmac
import threading
import time as time_module
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

# Supabase (use your Nditha project or create a new one)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://kfgutijhrywnxpsjjacd.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

RATE_LIMIT = 10
RATE_WINDOW_SECONDS = 60
MAX_HISTORY = 30

# ==================================================
# INITIALIZATION
# ==================================================
app = Flask(__name__)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_KEY else None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

logger.info("=" * 60)
logger.info("KANYOZA SYSTEMS BOT v5.0 - Human-Like AI")
logger.info(f"Gemini: {'✅' if GEMINI_KEY else '❌'}")
logger.info(f"Facebook: {'✅' if PAGE_ACCESS_TOKEN else '❌'}")
logger.info(f"Supabase: {'✅' if supabase else '❌ (memory disabled)'}")
logger.info("=" * 60)

# ==================================================
# ASYNC MESSAGE QUEUE
# ==================================================
message_queue = Queue()

def process_messages_worker():
    """Background worker that processes messages without blocking webhook"""
    while True:
        try:
            sender_id, text, message_id = message_queue.get()
            _process_single_message(sender_id, text, message_id)
            message_queue.task_done()
        except Exception as e:
            logger.error(f"Worker error: {e}")
            message_queue.task_done()

for i in range(4):
    threading.Thread(target=process_messages_worker, daemon=True).start()

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

Your knowledge:
- Deep expertise in software engineering, system architecture, databases
- Strong opinions on clean code, testing, and avoiding over-engineering
- Experience building tech solutions in African markets
- Understands the challenges of intermittent internet, offline-first design
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

PET_PEEVES = [
    "over-engineered solutions to simple problems",
    "people who don't write tests then complain about bugs",
    "meetings that should have been emails",
    "framework churn for no good reason",
    "premature optimization"
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

# ==================================================
# PERSONAL STORIES DATABASE
# ==================================================
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
        "triggers": ["learn", "study", "course", "tutorial"],
        "story": "The thing that taught me the most wasn't a course or tutorial. It was maintaining a 10-year-old codebase for 6 months. You learn architecture by seeing what happens when bad decisions age for a decade."
    },
    {
        "triggers": ["africa", "malawi", "local", "network", "internet"],
        "story": "Building software in Malawi teaches you things Silicon Valley engineers never consider. What happens when your users are on 2G? You learn offline-first design, tiny payloads, and graceful degradation. It makes you a better engineer."
    },
    {
        "triggers": ["startup", "business", "idea", "build"],
        "story": "I've learned that most startup ideas fail not because the tech is bad, but because nobody actually wanted the product. Now I always tell people: validate the problem before you build the solution. Talk to 20 real people first."
    },
    {
        "triggers": ["testing", "tests", "quality", "deploy"],
        "story": "I used to skip writing tests because I thought it slowed me down. Then I deployed a 'small fix' that broke the login page. On a Friday. At 5 PM. Now I write tests religiously. Trust me on this one."
    },
    {
        "triggers": ["meeting", "manager", "team", "lead"],
        "story": "The best tech lead I ever worked with never talked about code in meetings. She talked about trade-offs, timelines, and team morale. The code was the easy part. Managing humans is the real skill in software engineering."
    },
    {
        "triggers": ["api", "integration", "third party", "service"],
        "story": "I once built a system that depended on a third-party API. Then that API changed without warning. Now I always design with the assumption that external services will fail. Circuit breakers, fallbacks, graceful degradation — these aren't optional, they're essential."
    },
    {
        "triggers": ["security", "hack", "password", "data"],
        "story": "A client once stored passwords in plain text. When I showed them how easy it was to see everyone's passwords, they went pale. We fixed it that same day. I still use that story to explain why security matters, even for small projects."
    }
]

# ==================================================
# PREMIUM CONTENT ENGINE
# ==================================================
CONTENT_HOOKS = [
    # Failure lessons (highest engagement)
    "I cost a client $50,000 with one bad architectural decision. Here's what I learned:",
    "I almost lost my biggest client last year. The reason was embarrassing and preventable.",
    "Three years ago I was making junior dev mistakes. Last week I caught myself making the same one.",
    "My first production outage happened at 2 AM on a Saturday. I still remember the exact line of code.",
    
    # Controversial takes
    "Clean Code is overrated and I'm tired of pretending it's not.",
    "Your microservices are probably making your life harder, not easier.",
    "Most 'best practices' in tech are just opinions that survived long enough to become rules.",
    "We need to stop telling juniors to learn 10 technologies before applying for jobs.",
    
    # Curiosity gaps
    "The best debugging tool I've ever used isn't a debugger. It's something much simpler.",
    "I fixed a bug that had stumped our team for weeks. The solution took 30 seconds.",
    "There's a question I ask in every code review that seniors love and juniors find uncomfortable.",
    "One database setting. That's all it took to make our app 10x faster. Here's the setting:",
    
    # Direct value
    "Here's a system design pattern that's saved me at least 100 hours of refactoring:",
    "Stop writing complex code. This one principle changed how I build everything.",
    "I've interviewed 50 developers. Here's the one thing that separates the good from the great:",
    "Your error messages are terrible and they're costing you users. Here's how to fix them:"
]

CONTENT_FORMATS = {
    "lessons_learned": """
        Structure:
        1. Start with '{hook}'
        2. The Story (3-4 sentences, specific and real)
        3. What I Learned (numbered, 3-5 actionable points)
        4. The One Takeaway (single sentence, memorable)
        5. End with a question to spark discussion
        
        Tone: Like you're telling a story to a colleague over coffee.
        Length: 400-600 words.
        Format: Short paragraphs. Mobile-friendly. No hashtags unless meaningful.
    """,
    
    "controversial_take": """
        Structure:
        1. Start with '{hook}'
        2. State your opinion clearly (2-3 sentences)
        3. Back it up with 2-3 specific examples from your experience
        4. Acknowledge when the conventional wisdom IS right (show nuance)
        5. Invite discussion: "What's a tech opinion you hold that others disagree with?"
        
        Important: Be confident but not arrogant. Use "in my experience" and "I've found that."
        Goal: Spark thoughtful discussion, not prove you're right.
    """,
    
    "quick_win": """
        Structure:
        1. Start with '{hook}'
        2. The specific problem (one sentence)
        3. The solution (include code or commands if relevant)
        4. Why it works (brief technical explanation)
        5. Where to learn more
        
        Length: 200-300 words.
        Goal: Something they can use TODAY.
    """,
    
    "behind_the_scenes": """
        Structure:
        1. Start with '{hook}'
        2. What people think software engineering is
        3. What it actually is (specific example from your week)
        4. A moment that illustrates the reality
        5. Why this matters
        
        Goal: Make people feel seen. Show the human side of tech.
    """,
    
    "story_lesson": """
        Structure:
        1. Start with '{hook}'
        2. The Setup (context, what you were trying to do)
        3. The Complication (what went wrong or surprised you)
        4. The Turning Point (what you realized or tried differently)
        5. The Resolution (what happened)
        6. The Universal Lesson (applicable beyond tech)
        
        Length: 500-700 words.
        Goal: Make them feel like they were there.
    """
}

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
            
            # Persist to Supabase if available
            if supabase:
                try:
                    threading.Thread(target=self._persist_message, args=(sender_id, role, text)).start()
                except:
                    pass
    
    def _persist_message(self, sender_id, role, text):
        try:
            supabase.table('chat_history').insert({
                'sender_id': sender_id,
                'role': role,
                'text': text[:1000],
                'created_at': datetime.now().isoformat()
            }).execute()
        except:
            pass
    
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
# HUMAN BEHAVIOR SIMULATION
# ==================================================
def get_current_mood() -> str:
    """Get mood based on time of day"""
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
    """Calculate realistic response delay"""
    word_count = len(message.split())
    reading_time = (word_count / 200) * 60
    thinking_time = random.uniform(1.5, 6)
    response_length = random.randint(30, 200)
    typing_time = (response_length / 40) * 60
    total = reading_time + thinking_time + (typing_time * 0.3)
    total *= random.uniform(0.75, 1.5)
    return min(total, 20)

def humanize_response(text: str) -> str:
    """Make AI text read like casual human chat"""
    if not text:
        return text
    
    # Occasionally lowercase (casual mood)
    if random.random() < 0.15:
        text = text.lower()
    
    # Apply shortcuts naturally
    if random.random() < 0.4:
        for full, short in SHORTCUTS.items():
            if random.random() < 0.4 and full in text.lower():
                text = text.replace(full, short.capitalize() if text[0].isupper() else short)
    
    # Occasionally add fillers at the start
    if random.random() < 0.15 and len(text) > 50:
        filler = random.choice(CONVERSATIONAL_FILLERS)
        text = filler + text[0].lower() + text[1:]
    
    return text.strip()

def detect_sentiment(text: str) -> str:
    """Detect user sentiment"""
    text_lower = text.lower()
    angry = ["useless", "stupid", "hate", "angry", "frustrated", "terrible", "worst", "awful", "rubbish"]
    enthusiastic = ["love", "awesome", "great", "excellent", "amazing", "best", "fantastic", "wow", "brilliant"]
    
    if any(word in text_lower for word in angry):
        return "angry"
    elif any(word in text_lower for word in enthusiastic):
        return "enthusiastic"
    return "neutral"

def detect_language(text: str) -> str:
    """Detect Chichewa vs English"""
    chichewa_markers = ['ndi', 'kuti', 'zinthu', 'bwino', 'zikomo', 'muli', 'bwanji', 
                        'chifukwa', 'pamene', 'chonde', 'ndithu', 'ayi', 'inde']
    text_lower = text.lower()
    score = sum(1 for marker in chichewa_markers if marker in text_lower.split())
    return 'chichewa' if score >= 2 else 'english'

def find_relevant_story(message: str) -> Optional[str]:
    """Find a personal story relevant to the conversation"""
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
    """Build complete persona with current mood and context"""
    mood = get_current_mood()
    sentiment = storage.get_sentiment(sender_id)
    obsession = random.choice(TECH_OBSESSIONS)
    pet_peeve = random.choice(PET_PEEVES)
    
    persona = MADA_PERSONA_BASE
    
    if is_chichewa:
        persona += "\n\nYou are responding in Chichewa. Use natural, conversational Chichewa mixed with English technical terms where appropriate."
    
    persona += f"\n\nCurrent state: {mood}"
    persona += f"\nYou've been thinking about {obsession} lately."
    persona += f"\nYou're slightly annoyed by {pet_peeve} today."
    
    if sentiment == "angry":
        persona += "\n\nUser seems frustrated. Be extra patient, understanding, and helpful."
    elif sentiment == "enthusiastic":
        persona += "\n\nUser is excited. Match their positive energy."
    
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
    """Query Gemini with full human-like persona"""
    try:
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
            
            # Check for story opportunity
            story = find_relevant_story(user_message)
            story_instruction = f"\n\nIf natural, you could share this experience: {story}" if story else ""
            
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
            logger.error(f"[GEMINI ERROR] {result['error']}")
            return "Busy right now, leave your message and I'll get back to you!"
        
        candidates = result.get("candidates", [])
        if not candidates:
            return "Zikomo for your message! I'm a bit tied up but will respond properly soon."
        
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return "Interesting point — let me think about that and come back to you."
        
        reply = parts[0]["text"].strip()
        
        # Humanize the response
        if not is_cron:
            reply = humanize_response(reply)
            storage.add_to_memory(sender_id, "user", user_message)
            storage.add_to_memory(sender_id, "assistant", reply)
        
        return reply
        
    except Exception as e:
        logger.error(f"Gemini failed: {e}")
        return "I'm having network issues right now. Try again in a moment!"

# ==================================================
# PREMIUM CONTENT GENERATION
# ==================================================
@smart_retry(max_retries=2, base_delay=2.0)
def generate_premium_post() -> Optional[str]:
    """Generate high-quality, engaging professional content"""
    hook = random.choice(CONTENT_HOOKS)
    format_name = random.choice(list(CONTENT_FORMATS.keys()))
    format_instructions = CONTENT_FORMATS[format_name].replace('{hook}', hook)
    
    logger.info(f"[CONTENT] Generating {format_name} post")
    
    prompt = f"""
    You are Madalitso Kanyoza, a senior software engineer from Malawi sharing professional insights on Facebook.
    
    Write a post following these instructions exactly:
    
    {format_instructions}
    
    Critical rules:
    - This must sound like a real person sharing hard-earned wisdom
    - Be specific. Use real numbers, real tools, real scenarios
    - No motivational fluff. No "follow your dreams" nonsense
    - Technical enough to be useful, accessible enough to be readable
    - Write like you're talking to smart colleagues, not teaching children
    - Never use phrases like "in today's digital age" or "leveraging synergies"
    
    Make it so good that people save this post.
    """
    
    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.85, "maxOutputTokens": 900, "topP": 0.95}
            },
            timeout=45
        )
        result = response.json()
        
        if result.get("candidates"):
            post = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            word_count = len(post.split())
            logger.info(f"[CONTENT] Generated {word_count} words ({format_name})")
            
            if word_count < 100:
                return None
            return post
        return None
    except Exception as e:
        logger.error(f"[CONTENT] Generation failed: {e}")
        return None

def get_fallback_post() -> str:
    """Fallback if Gemini fails"""
    hook = random.choice(CONTENT_HOOKS)
    idea = random.choice([
        "Always design your APIs with versioning from day one. Retrofitting versioning is painful and breaks client integrations.",
        "Isolate your database behind a service layer. Direct database access from multiple services creates coupling nightmares.",
        "Implement circuit breakers for all external service calls. One slow third-party API shouldn't bring down your entire system.",
        "Write self-documenting code. If you need a comment to explain WHAT the code does, your function is probably too complex.",
        "Regularly audit your dependencies. I found a 2-year-old unpatched vulnerability in a client's project last month."
    ])
    return f"{hook}\n\n{idea}\n\nWhat's a lesson you learned the hard way? Share below — I'd love to hear your experience."

# ==================================================
# FACEBOOK API
# ==================================================
@smart_retry(max_retries=3, base_delay=1.0)
def send_messenger(recipient_psid: str, message: str):
    """Send message via Facebook Messenger"""
    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {"recipient": {"id": recipient_psid}, "message": {"text": message[:2000]}}
    response = requests.post(url, json=payload, timeout=30)
    if response.status_code != 200:
        logger.error(f"[SEND ERROR] {response.json()}")

def send_typing_on(recipient_psid: str):
    """Show typing indicator"""
    try:
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        requests.post(url, json={
            "recipient": {"id": recipient_psid},
            "sender_action": "typing_on"
        }, timeout=5)
    except:
        pass

def send_typing_off(recipient_psid: str):
    """Stop typing indicator"""
    try:
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        requests.post(url, json={
            "recipient": {"id": recipient_psid},
            "sender_action": "typing_off"
        }, timeout=5)
    except:
        pass

@smart_retry(max_retries=3, base_delay=2.0)
def post_to_page(message: str) -> bool:
    """Publish post to Facebook Page"""
    url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/feed"
    payload = {"message": message, "access_token": PAGE_ACCESS_TOKEN}
    response = requests.post(url, data=payload, timeout=30)
    result = response.json()
    if "id" in result:
        logger.info(f"[POST] Published! ID: {result['id']}")
        storage.set_last_post_time(datetime.now())
        return True
    logger.error(f"[POST ERROR] {result.get('error', {}).get('message')}")
    return False

# ==================================================
# MESSAGE PROCESSING
# ==================================================
def _process_single_message(sender_id: str, text: str, message_id: str = None):
    """Process one message (runs in worker thread)"""
    try:
        # Detect language
        language = detect_language(text)
        storage.set_language(sender_id, language)
        
        # Detect sentiment
        sentiment = detect_sentiment(text)
        storage.set_sentiment(sender_id, sentiment)
        
        # Calculate human delay
        delay = human_delay(text)
        logger.info(f"[PROCESSING] From {sender_id}: {text[:50]}... (delay: {delay:.1f}s, lang: {language})")
        
        # Wait like a human
        time_module.sleep(delay)
        
        # Show typing
        send_typing_on(sender_id)
        
        # Generate response
        reply = ask_gemini(sender_id, text)
        
        # Sometimes send as multiple messages (feels more human)
        if len(reply) > 500 and random.random() < 0.3:
            parts = reply.split('\n\n', 1)
            if len(parts) == 2:
                send_messenger(sender_id, parts[0])
                time_module.sleep(random.uniform(2, 5))
                send_typing_on(sender_id)
                time_module.sleep(random.uniform(1, 3))
                send_messenger(sender_id, parts[1])
                return
        
        send_messenger(sender_id, reply)
        
    except Exception as e:
        logger.error(f"Message processing failed: {e}")
        try:
            send_messenger(sender_id, "Sorry, something went wrong. Can you try again?")
        except:
            pass

# ==================================================
# AUTO-POST SCHEDULER
# ==================================================
def four_hour_auto_post():
    """Generate and publish premium post"""
    logger.info("[AUTO-POST] Generating premium content...")
    
    post_content = generate_premium_post()
    
    if not post_content:
        logger.warning("[AUTO-POST] Using fallback post")
        post_content = get_fallback_post()
    
    success = post_to_page(post_content)
    if success:
        logger.info("[AUTO-POST] Published successfully!")
    else:
        logger.error("[AUTO-POST] Failed to publish")

def scheduler_loop():
    """Background scheduler for auto-posting"""
    time_module.sleep(10)
    logger.info("[SCHEDULER] Started")
    
    while True:
        try:
            now = datetime.now()
            # Post at optimal times: 7:30, 12:30, 17:30, 20:30 CAT
            should_post = now.hour in [7, 12, 17, 20] and 25 <= now.minute <= 35
            
            if should_post:
                last = storage.get_last_post_time()
                if not last or (now - last) > timedelta(hours=3):
                    four_hour_auto_post()
            
            time_module.sleep(300)  # Check every 5 minutes
        except Exception as e:
            logger.error(f"[SCHEDULER ERROR] {e}")
            time_module.sleep(300)

cron_thread = threading.Thread(target=scheduler_loop, daemon=True)
cron_thread.start()

# ==================================================
# WEBHOOK VERIFICATION (Security)
# ==================================================
def verify_facebook_signature():
    """Verify requests are actually from Facebook"""
    if not APP_SECRET:
        return True  # Skip verification if no secret configured
    
    signature = request.headers.get('X-Hub-Signature-256', '')
    if not signature:
        logger.warning("[SECURITY] Missing signature header")
        return False
    
    expected = hmac.new(
        APP_SECRET.encode('utf-8'),
        request.data,
        hashlib.sha256
    ).hexdigest()
    
    expected_signature = f'sha256={expected}'
    return hmac.compare_digest(expected_signature, signature)

# ==================================================
# FLASK ROUTES
# ==================================================
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    if request.args.get("hub.mode") == "subscribe":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Verification token mismatch", 403
    return "OK", 200

@app.route("/webhook", methods=["POST"])
def receive_message():
    # Verify signature
    if not verify_facebook_signature():
        logger.warning("[SECURITY] Invalid signature — request rejected")
        return "Invalid signature", 403
    
    data = request.get_json()
    
    try:
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):
                sender_id = event["sender"]["id"]
                message_id = event.get("message", {}).get("mid")
                
                # Deduplication
                if message_id and storage.is_duplicate(message_id):
                    continue
                
                # Handle text messages
                if "message" in event and "text" in event["message"]:
                    text = event["message"]["text"].strip()
                    logger.info(f"[INBOUND] {sender_id}: {text[:80]}")
                    
                    # Rate limiting
                    if storage.check_rate_limit(sender_id):
                        send_messenger(sender_id, "⏳ You're sending messages too fast. Give me a moment to catch up.")
                        continue
                    
                    # Owner commands
                    if sender_id == OWNER_PSID:
                        if text.lower() == "!stop":
                            storage.set_paused(sender_id, True)
                            send_messenger(sender_id, "🤖 Bot paused for 30 minutes.")
                            continue
                        elif text.lower() == "!start":
                            storage.set_paused(sender_id, False)
                            send_messenger(sender_id, "🤖 Bot resumed.")
                            continue
                        elif text.lower() == "!post":
                            send_messenger(sender_id, "⚙️ Generating premium post now...")
                            threading.Thread(target=four_hour_auto_post).start()
                            continue
                        elif text.lower() == "!stats":
                            stats = storage.__dict__.get('chat_memory', {})
                            send_messenger(sender_id, f"📊 Active chats: {len(stats)}")
                            continue
                    
                    # Skip if paused
                    if storage.is_paused(sender_id):
                        continue
                    
                    # Queue for async processing
                    message_queue.put((sender_id, text, message_id))
                    
    except Exception as e:
        logger.error(f"[ROUTE ERROR] {e}")
    
    return "EVENT_RECEIVED", 200

@app.route("/status", methods=["GET"])
def system_status():
    return jsonify({
        "status": "online",
        "version": "5.0.0",
        "model": GEMINI_MODEL,
        "supabase": "connected" if supabase else "not configured",
        "last_post": str(storage.get_last_post_time()),
        "active_chats": len(storage.chat_memory),
        "queue_size": message_queue.qsize()
    })

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "Kanyoza Systems Bot v5.0",
        "status": "operational"
    })

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
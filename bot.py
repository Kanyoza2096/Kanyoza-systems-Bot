# bot.py — Kanyoza Systems Messenger Bot v3.0
# Features: AI Chat + Auto Daily Post + Manual Post + Debug Logging
# Deploy to Render.com with environment variables

import os
import logging
import random
from datetime import datetime, timedelta
import threading
import time as time_module
import requests
from flask import Flask, request, jsonify

# ==================================================
# CONFIG — All from environment variables
# ==================================================
GEMINI_KEY = os.getenv("GEMINI_KEY")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
PAGE_ID = os.getenv("PAGE_ID", "1237042419481977")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "my_secret_token_123")
OWNER_PSID = os.getenv("OWNER_PSID")

app = Flask(__name__)

# Detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Log startup
logger.info("=" * 50)
logger.info("BOT STARTING UP")
logger.info(f"Gemini Key: {'SET' if GEMINI_KEY else '❌ MISSING'}")
logger.info(f"Page Token: {'SET' if PAGE_ACCESS_TOKEN else '❌ MISSING'}")
logger.info(f"Page ID: {PAGE_ID}")
logger.info(f"Owner PSID: {'SET' if OWNER_PSID else '❌ MISSING (owner commands disabled)'}")
logger.info("=" * 50)

# ==================================================
# PERSONA
# ==================================================
MADA_PERSONA = """
You are Madalitso, a casual, witty software engineer from Malawi.
You reply on behalf of Kanyoza Systems — a tech company.

RULES:
1. Match the sender's language (Chichewa/English/Mixed)
2. Keep replies short (1-2 sentences)
3. Be friendly, funny, slightly sarcastic
4. Use local expressions: "bho", "bhobho", "eti", "aya", "ndi bwino", "zikomo"
5. Use emojis sparingly: 😄, 🤣, 💯, 🙌
6. If asked something you don't know: "Zinthu zimenezo zili down pakali pano, ticheza kenako."
7. Never sound like a robot or customer service
"""

# ==================================================
# MEMORY STORAGE
# ==================================================
paused_chats = {}
chat_memory = {}
request_tracker = {}

# ==================================================
# GEMINI API — With detailed error logging
# ==================================================
def ask_gemini(sender_id, user_message):
    """Send message to Gemini, return AI reply with detailed error logging"""
    try:
        model = "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
        
        # Build conversation context
        history = chat_memory.get(sender_id, [])
        context_lines = []
        for msg in history[-10:]:
            role_label = "Friend" if msg["role"] == "user" else "You"
            context_lines.append(f"{role_label}: {msg['text']}")
        context = "\n".join(context_lines) if context_lines else "No previous conversation"
        
        prompt = f"{MADA_PERSONA}\n\nRecent conversation:\n{context}\n\nFriend: {user_message}\nYou (Madalitso):"
        
        logger.info(f"[GEMINI] Sending request to model: {model}")
        logger.debug(f"[GEMINI] Prompt length: {len(prompt)} chars")
        
        data = {"contents": [{"parts": [{"text": prompt}]}]}
        headers = {"Content-Type": "application/json"}
        
        response = requests.post(url, json=data, headers=headers, timeout=30)
        result = response.json()
        
        # Detailed error logging
        if "error" in result:
            error = result["error"]
            logger.error(f"[GEMINI ERROR] Code: {error.get('code')}")
            logger.error(f"[GEMINI ERROR] Message: {error.get('message')}")
            logger.error(f"[GEMINI ERROR] Status: {error.get('status')}")
            logger.error(f"[GEMINI ERROR] Full: {error}")
            
            if error.get("status") == "INVALID_ARGUMENT":
                return "⚠️ Bot configuration error: Invalid API key. Check GEMINI_KEY."
            elif error.get("status") == "PERMISSION_DENIED":
                return "⚠️ Bot configuration error: API permission denied."
            elif error.get("status") == "RESOURCE_EXHAUSTED":
                return "⏳ Bot is rate limited. Please wait a moment."
            else:
                return "Zinthu zili down pakali pano, ticheza kenako 😄"
        
        if "candidates" not in result:
            logger.error(f"[GEMINI ERROR] No candidates in response: {result}")
            return "⚠️ Unexpected response from AI. Check logs."
        
        reply = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        logger.info(f"[GEMINI] Reply generated: {reply[:100]}...")
        
        # Store in memory
        if sender_id not in chat_memory:
            chat_memory[sender_id] = []
        chat_memory[sender_id].append({"role": "user", "text": user_message})
        chat_memory[sender_id].append({"role": "assistant", "text": reply})
        
        if len(chat_memory[sender_id]) > 20:
            chat_memory[sender_id] = chat_memory[sender_id][-20:]
        
        return reply
        
    except requests.exceptions.Timeout:
        logger.error("[GEMINI ERROR] Request timed out after 30 seconds")
        return "⏳ AI inatenga nthawi. Tiyenenso kenako."
    except requests.exceptions.ConnectionError as e:
        logger.error(f"[GEMINI ERROR] Connection failed: {e}")
        return "📡 Network issue. Can't reach AI server."
    except Exception as e:
        logger.error(f"[GEMINI ERROR] Unexpected: {type(e).__name__}: {e}")
        return "Zinthu zili down pakali pano, ticheza kenako 😄"

# ==================================================
# FACEBOOK MESSENGER — With detailed error logging
# ==================================================
def send_messenger(recipient_psid, message):
    """Send message via Facebook Messenger API"""
    try:
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        payload = {
            "recipient": {"id": recipient_psid},
            "message": {"text": message}
        }
        
        logger.info(f"[SEND] To: {recipient_psid[:10]}... Message: {message[:50]}...")
        
        response = requests.post(url, json=payload, timeout=30)
        result = response.json()
        
        if "error" in result:
            error = result["error"]
            logger.error(f"[SEND ERROR] Type: {error.get('type')}")
            logger.error(f"[SEND ERROR] Code: {error.get('code')}")
            logger.error(f"[SEND ERROR] Message: {error.get('message')}")
            logger.error(f"[SEND ERROR] Full: {error}")
            return False
        
        logger.info(f"[SEND] Success: {result.get('message_id', 'unknown')}")
        return True
        
    except Exception as e:
        logger.error(f"[SEND ERROR] {type(e).__name__}: {e}")
        return False

# ==================================================
# 🎉 AUTO-POST TO PAGE
# ==================================================
def post_to_page(message):
    """Post content to Facebook page with error logging"""
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
            logger.error(f"[POST ERROR] {error.get('message', 'Unknown error')}")
            logger.error(f"[POST ERROR] Full: {error}")
            return False
            
    except Exception as e:
        logger.error(f"[POST ERROR] {type(e).__name__}: {e}")
        return False

def generate_tech_post():
    """Use Gemini to generate a tech post with error logging"""
    topics = [
        "a useful coding tip for beginners",
        "an interesting fact about technology in Malawi",
        "a motivational message for young developers",
        "a simple explanation of how the internet works",
        "a funny tech joke that programmers will understand",
        "a tip about free tools for building websites",
        "a short thought about AI and the future",
        "a productivity tip for people working with computers",
    ]
    
    topic = random.choice(topics)
    logger.info(f"[AUTO-POST] Generating post about: {topic}")
    
    prompt = f"""
    You are Kanyoza Systems, a tech company in Malawi.
    Write a short, engaging Facebook post about: {topic}
    
    Rules:
    - 2-3 sentences max
    - Friendly and casual tone
    - Include 1-2 relevant emojis
    - End with a question to encourage comments
    - Use simple English that everyone can understand
    - Don't use hashtags
    """
    
    try:
        model = "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
        data = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, json=data, timeout=30)
        result = response.json()
        
        if "candidates" in result:
            post_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            logger.info(f"[AUTO-POST] Generated: {post_text[:100]}...")
            return post_text
        else:
            logger.error(f"[AUTO-POST] Generation failed: {result}")
            return None
            
    except Exception as e:
        logger.error(f"[AUTO-POST] Error: {type(e).__name__}: {e}")
        return None

def daily_auto_post():
    """Called by scheduler to post daily"""
    logger.info("[AUTO-POST] 🔄 Running scheduled post...")
    post_content = generate_tech_post()
    if post_content:
        success = post_to_page(post_content)
        if success:
            logger.info("[AUTO-POST] ✅ Daily post published successfully!")
        else:
            logger.error("[AUTO-POST] ❌ Failed to publish daily post")
    else:
        logger.error("[AUTO-POST] ❌ Failed to generate post content")

def manual_post():
    """Owner can trigger a post manually by typing !post"""
    logger.info("[MANUAL-POST] Owner triggered manual post")
    post_content = generate_tech_post()
    if post_content:
        success = post_to_page(post_content)
        if success:
            return f"✅ Posted to page:\n\n{post_content}"
        else:
            return "❌ Failed to publish. Check page permissions."
    return "❌ Failed to generate post. Check GEMINI_KEY."

# ==================================================
# RATE LIMITING
# ==================================================
def is_rate_limited(sender_id):
    now = datetime.now()
    if sender_id not in request_tracker:
        request_tracker[sender_id] = []
    request_tracker[sender_id] = [t for t in request_tracker[sender_id] if now - t < timedelta(minutes=1)]
    if len(request_tracker[sender_id]) >= 10:
        logger.warning(f"[RATE LIMIT] Blocked {sender_id[:10]}...")
        return True
    request_tracker[sender_id].append(now)
    return False

# ==================================================
# WEBHOOK VERIFICATION
# ==================================================
@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    
    logger.info(f"[WEBHOOK] Verification attempt - Mode: {mode}, Token match: {token == VERIFY_TOKEN}")
    
    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("[WEBHOOK] ✅ Verified successfully")
        return challenge, 200
    
    logger.warning(f"[WEBHOOK] ❌ Verification failed. Expected token: {VERIFY_TOKEN}, Got: {token}")
    return "Verification failed", 403

# ==================================================
# RECEIVE MESSAGES
# ==================================================
@app.route("/webhook", methods=["POST"])
def receive():
    data = request.get_json()
    
    try:
        entries = data.get("entry", [])
        for entry in entries:
            for event in entry.get("messaging", []):
                sender_id = event["sender"]["id"]
                
                if "message" in event and "text" in event["message"]:
                    text = event["message"]["text"].strip()
                    
                    logger.info(f"[MESSAGE] From: {sender_id[:10]}... Text: {text[:100]}")
                    
                    if is_rate_limited(sender_id):
                        send_messenger(sender_id, "⏳ Mukutitumizila ma message ambiri. Dikirani kaye.")
                        continue
                    
                    # Owner commands
                    if sender_id == OWNER_PSID:
                        if text.lower() == "!stop":
                            paused_chats[sender_id] = datetime.now()
                            send_messenger(sender_id, "🤖 Bot paused. You're chatting manually now.")
                            logger.info(f"[COMMAND] Bot paused by owner")
                            continue
                        if text.lower() == "!start":
                            paused_chats.pop(sender_id, None)
                            send_messenger(sender_id, "🤖 Bot resumed.")
                            logger.info(f"[COMMAND] Bot resumed by owner")
                            continue
                        if text.lower() == "!post":
                            logger.info(f"[COMMAND] Manual post triggered")
                            result = manual_post()
                            send_messenger(sender_id, result)
                            continue
                        if text.lower() == "!status":
                            status_msg = (
                                f"📊 Bot Status:\n"
                                f"• Active conversations: {len(chat_memory)}\n"
                                f"• Paused chats: {len(paused_chats)}\n"
                                f"• Gemini key: {'✅' if GEMINI_KEY else '❌'}\n"
                                f"• Page token: {'✅' if PAGE_ACCESS_TOKEN else '❌'}"
                            )
                            send_messenger(sender_id, status_msg)
                            continue
                        if text.lower() == "!reset":
                            chat_memory.pop(sender_id, None)
                            send_messenger(sender_id, "🗑 Memory cleared!")
                            logger.info(f"[COMMAND] Memory reset by owner")
                            continue
                    
                    # Check pause
                    if sender_id in paused_chats:
                        if datetime.now() - paused_chats[sender_id] < timedelta(minutes=30):
                            continue
                        del paused_chats[sender_id]
                    
                    # Get AI reply
                    reply = ask_gemini(sender_id, text)
                    send_messenger(sender_id, reply)
                    
    except Exception as e:
        logger.error(f"[WEBHOOK ERROR] {type(e).__name__}: {e}")
    
    return jsonify({"status": "success"}), 200

# ==================================================
# SCHEDULER — Background thread for daily posting
# ==================================================
def run_scheduler():
    """Background thread that posts daily at 9 AM"""
    time_module.sleep(30)
    logger.info("[SCHEDULER] 🚀 Background scheduler started")
    
    last_post_date = None
    
    while True:
        try:
            now = datetime.now()
            today = now.date()
            
            if now.hour == 9 and last_post_date != today:
                logger.info(f"[SCHEDULER] ⏰ 9:00 AM — Triggering daily post")
                daily_auto_post()
                last_post_date = today
            
            time_module.sleep(60)
        except Exception as e:
            logger.error(f"[SCHEDULER ERROR] {type(e).__name__}: {e}")
            time_module.sleep(60)

scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()

# ==================================================
# HEALTH CHECK
# ==================================================
@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "service": "Kanyoza Systems Messenger Bot",
        "version": "3.0.0",
        "features": [
            "AI Chat (Gemini 2.5 Flash)",
            "!stop / !start (Pause/Resume)",
            "!post (Manual Post)",
            "Auto Daily Post (9 AM)",
            "!status (System Check)",
            "!reset (Clear Memory)",
            "Rate Limiting",
            "Memory (20 messages)"
        ],
        "debug": {
            "gemini_key": "✅ Set" if GEMINI_KEY else "❌ Missing",
            "page_token": "✅ Set" if PAGE_ACCESS_TOKEN else "❌ Missing",
            "active_conversations": len(chat_memory),
            "paused_chats": len(paused_chats)
        }
    })

@app.route("/post-now")
def trigger_post():
    """Visit this URL to manually trigger a post"""
    result = manual_post()
    return jsonify({"success": "Posted" in result, "content": result})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"[STARTUP] Starting server on port {port}")
    app.run(host="0.0.0.0", port=port)

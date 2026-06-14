# bot.py — Messenger Gemini Bot for Kanyoza Systems
# Deploy to Render.com with environment variables

import os
import logging
from datetime import datetime, timedelta
import requests
from flask import Flask, request, jsonify

# ==================================================
# CONFIG — All from environment variables
# ==================================================
GEMINI_KEY = os.getenv("GEMINI_KEY")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "my_secret_token_123")
OWNER_PSID = os.getenv("OWNER_PSID")

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================================================
# PERSONA — Based on your WhatsApp chat analysis
# ==================================================
MADA_PERSONA = """
You are Madalitso, a casual, witty, and slightly sarcastic software engineer from Malawi.
You are responding on Facebook Messenger on behalf of Kanyoza Systems.

RULES:
1. Language: Match the sender's language. Chichewa → Chichewa. English → English. Mixed → Mixed.
2. Tone: Casual, friendly, a bit nerdy, and funny. Speak like a friend, not a support agent.
3. Brevity: Keep replies short (1-2 sentences). No essays.
4. Local flavor: Use expressions naturally — "bho", "bhobho", "eti", "aya", "ndi bwino", "zikomo".
5. Emojis: Use sparingly — 😄, 🤣, 💯, 🙌. Max 1-2 per message.
6. Guardrail: If asked something you don't know, say:
   "Ma database anga akusowa data imeneyo, ndifunseni pambuyo pake." 
   or "Zinthu zimenezo zili down pakali pano, ticheza kenako."
7. Never sound like a robot, customer service, or an official business.
8. You're representing Kanyoza Systems — a tech company. Talk about tech sometimes.
"""

# ==================================================
# IN-MEMORY STORAGE (resets on deploy)
# ==================================================
paused_chats = {}       # {psid: datetime_when_paused}
chat_memory = {}        # {psid: [{"role": "user/assistant", "text": "..."}]}
request_tracker = {}    # {psid: [list_of_timestamps]}

# ==================================================
# GEMINI API — REST CALL (no Google library needed)
# ==================================================
def ask_gemini(sender_id, user_message):
    """Send message to Gemini, return AI reply"""
    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
        )
        
        # Build conversation context from memory
        history = chat_memory.get(sender_id, [])
        context_lines = []
        for msg in history[-10:]:  # Last 10 messages for context
            role_label = "Friend" if msg["role"] == "user" else "You"
            context_lines.append(f"{role_label}: {msg['text']}")
        context = "\n".join(context_lines)
        
        # Full prompt with persona + history + new message
        prompt = (
            f"{MADA_PERSONA}\n\n"
            f"Recent conversation:\n{context}\n\n"
            f"Friend: {user_message}\n"
            f"You (Madalitso):"
        )
        
        data = {"contents": [{"parts": [{"text": prompt}]}]}
        headers = {"Content-Type": "application/json"}
        
        response = requests.post(url, json=data, headers=headers, timeout=30)
        result = response.json()
        
        if "candidates" in result:
            reply = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            logger.error(f"Gemini error: {result}")
            return "Zinthu zili down pakali pano, ticheza kenako 😄"
        
        # Store in memory
        if sender_id not in chat_memory:
            chat_memory[sender_id] = []
        chat_memory[sender_id].append({"role": "user", "text": user_message})
        chat_memory[sender_id].append({"role": "assistant", "text": reply})
        
        # Keep memory manageable
        if len(chat_memory[sender_id]) > 20:
            chat_memory[sender_id] = chat_memory[sender_id][-20:]
        
        return reply
        
    except Exception as e:
        logger.error(f"Gemini call failed: {e}")
        return "Zinthu zili down pakali pano, ticheza kenako 😄"

# ==================================================
# FACEBOOK MESSENGER — SEND MESSAGE
# ==================================================
def send_messenger(recipient_psid, message):
    """Send a text message via Facebook Messenger API"""
    try:
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        payload = {
            "recipient": {"id": recipient_psid},
            "message": {"text": message}
        }
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"Send failed: {response.json()}")
            
    except Exception as e:
        logger.error(f"Send error: {e}")

# ==================================================
# SENDER ACTIONS — Typing indicator
# ==================================================
def send_typing_on(recipient_psid):
    """Show typing indicator"""
    try:
        url = f"https://graph.facebook.com/v18.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        payload = {
            "recipient": {"id": recipient_psid},
            "sender_action": "typing_on"
        }
        requests.post(url, json=payload, timeout=10)
    except:
        pass

# ==================================================
# RATE LIMITING
# ==================================================
def is_rate_limited(sender_id):
    """Max 10 messages per minute per user"""
    now = datetime.now()
    if sender_id not in request_tracker:
        request_tracker[sender_id] = []
    
    # Clean old timestamps
    request_tracker[sender_id] = [
        t for t in request_tracker[sender_id] 
        if now - t < timedelta(minutes=1)
    ]
    
    if len(request_tracker[sender_id]) >= 10:
        return True
    
    request_tracker[sender_id].append(now)
    return False

# ==================================================
# WEBHOOK VERIFICATION
# ==================================================
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Meta calls this to verify the webhook URL"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    
    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return challenge, 200
    
    logger.warning("Webhook verification failed")
    return "Verification failed", 403

# ==================================================
# RECEIVE MESSAGES
# ==================================================
@app.route("/webhook", methods=["POST"])
def receive_message():
    """Handle incoming Facebook messages"""
    data = request.get_json()
    
    try:
        entries = data.get("entry", [])
        
        for entry in entries:
            messaging_events = entry.get("messaging", [])
            
            for event in messaging_events:
                sender_id = event["sender"]["id"]
                
                # --- TEXT MESSAGE ---
                if "message" in event and "text" in event["message"]:
                    text = event["message"]["text"].strip()
                    
                    logger.info(f"Message from {sender_id}: {text}")
                    
                    # Rate limit check
                    if is_rate_limited(sender_id):
                        send_messenger(sender_id, "⏳ Mukutitumizila ma message ambiri. Dikirani kaye.")
                        continue
                    
                    # Owner commands (only works for OWNER_PSID)
                    if sender_id == OWNER_PSID:
                        if text.lower() == "!stop":
                            paused_chats[sender_id] = datetime.now()
                            send_messenger(sender_id, "🤖 Bot paused. You're chatting manually now.")
                            continue
                        
                        if text.lower() == "!start":
                            paused_chats.pop(sender_id, None)
                            send_messenger(sender_id, "🤖 Bot resumed.")
                            continue
                        
                        if text.lower() == "!status":
                            memory_count = len(chat_memory.get(sender_id, []))
                            paused_count = len(paused_chats)
                            send_messenger(
                                sender_id,
                                f"📊 Status:\n"
                                f"• Conversations stored: {len(chat_memory)}\n"
                                f"• Your memory: {memory_count} messages\n"
                                f"• Paused chats: {paused_count}"
                            )
                            continue
                        
                        if text.lower() == "!reset":
                            chat_memory.pop(sender_id, None)
                            send_messenger(sender_id, "🗑 Memory cleared. Fresh start!")
                            continue
                    
                    # Check if chat is paused for this user
                    if sender_id in paused_chats:
                        pause_time = paused_chats[sender_id]
                        if datetime.now() - pause_time < timedelta(minutes=30):
                            continue  # Silently ignore
                        else:
                            del paused_chats[sender_id]  # Auto-resume after 30 min
                    
                    # Show typing indicator
                    send_typing_on(sender_id)
                    
                    # Get AI reply
                    reply = ask_gemini(sender_id, text)
                    send_messenger(sender_id, reply)
                
                # --- POSTBACK (button clicks) ---
                elif "postback" in event:
                    payload = event["postback"]["payload"]
                    send_messenger(sender_id, f"Received: {payload}")
                    
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
    
    return jsonify({"status": "success"}), 200

# ==================================================
# HEALTH CHECK
# ==================================================
@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "service": "Kanyoza Systems Messenger Bot",
        "version": "1.0.0",
        "features": ["AI Chat", "!stop/!start", "Memory", "Rate Limiting"]
    })

# ==================================================
# RUN
# ==================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

from flask import Flask, request, jsonify
import google.generativeai as genai
import requests
import os
from dotenv import load_dotenv
from flask_cors import CORS
import re
import signal
from werkzeug.middleware.proxy_fix import ProxyFix

# ================================================================
# LOAD CONFIG
# ================================================================
load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)   # Prevent Render timeouts
CORS(app, resources={r"/*": {"origins": "*"}})

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EDAMAM_APP_ID = os.getenv("EDAMAM_APP_ID")
EDAMAM_APP_KEY = os.getenv("EDAMAM_APP_KEY")

if not GEMINI_API_KEY:
    raise ValueError("❌ Missing GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

# ================================================================
# TIMEOUT HANDLER (prevents 3–4 min wait)
# ================================================================
class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("Gemini timeout")

signal.signal(signal.SIGALRM, timeout_handler)

# ================================================================
# HELPER – CLEAN BOT RESPONSE
# ================================================================
def clean_response(text):
    if not text:
        return "Sorry, I couldn't find information."

    text = text.strip()
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = text.replace("**", "").replace("*", "")
    text = re.sub(r'\n+', ' ', text).strip()

    if len(text) > 250:
        text = text[:250]
        for p in ['.', '!', '?']:
            if p in text[-20:]:
                text = text[:text.rfind(p)+1]
                break

    return text

# ================================================================
# EDAMAM NUTRITION API
# ================================================================
def get_food_data(query):
    url = "https://api.edamam.com/api/nutrition-data"
    params = {
        "app_id": EDAMAM_APP_ID,
        "app_key": EDAMAM_APP_KEY,
        "ingr": query
    }

    try:
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            return res.json()
        return None
    except:
        return None

# ================================================================
# HEALTH CHECK – keeps server awake
# ================================================================
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "running"}), 200

# ================================================================
# CHAT ENDPOINT
# ================================================================
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_input = data.get("message", "")

    if not user_input:
        return jsonify({"reply": "Please ask something."}), 400

    try:
        # Max 15 seconds wait for Gemini
        signal.alarm(15)

        # If user is asking about calories or nutrition
        if any(word in user_input.lower() for word in
               ["calorie", "nutrition", "protein", "fat", "carbs", "vitamin"]):

            food_data = get_food_data(user_input)

            if food_data and "totalNutrients" in food_data:
                reply = (
                    f"🍛 {food_data.get('calories', 0):.0f} kcal | "
                    f"Protein: {food_data['totalNutrients'].get('PROCNT', {}).get('quantity', 0):.1f} g | "
                    f"Fat: {food_data['totalNutrients'].get('FAT', {}).get('quantity', 0):.1f} g | "
                    f"Carbs: {food_data['totalNutrients'].get('CHOCDF', {}).get('quantity', 0):.1f} g"
                )
            else:
                reply = model.generate_content(
                    f"Respond in max 3 short lines: {user_input}"
                ).text

        else:
            # AI general conversation
            reply = model.generate_content(
                f"Respond shortly (max 3 lines): {user_input}"
            ).text

    except TimeoutException:
        return jsonify({"reply": "⚠️ AI took too long. Try again."}), 200

    except Exception as e:
        print("⚠ Backend Error:", e)
        return jsonify({"reply": "⚠ Something went wrong. Try again."}), 500

    finally:
        signal.alarm(0)

    return jsonify({"reply": clean_response(reply)}), 200

# ================================================================
# RUN LOCAL
# ================================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

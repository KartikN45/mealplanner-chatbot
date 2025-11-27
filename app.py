from flask import Flask, request, jsonify
import google.generativeai as genai
import requests
import os
from dotenv import load_dotenv
from flask_cors import CORS
import re

# --- Load environment variables ---
load_dotenv()

app = Flask(__name__)
CORS(app)

# Environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EDAMAM_APP_ID = os.getenv("EDAMAM_APP_ID")
EDAMAM_APP_KEY = os.getenv("EDAMAM_APP_KEY")

# Validate keys
if not GEMINI_API_KEY:
    raise ValueError("❌ Missing GEMINI_API_KEY in environment variables.")
if not EDAMAM_APP_ID or not EDAMAM_APP_KEY:
    raise ValueError("❌ Missing EDAMAM_APP_ID or EDAMAM_APP_KEY in environment variables.")

# --- Configure Gemini ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# --- Helper: Clean AI response ---
def clean_response(text):
    """Clean and force the response to 2–3 lines max."""
    if not text:
        return "Sorry, I couldn’t find relevant information."

    text = text.strip()
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = text.replace("**", "").replace("*", "")
    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)

    # max 250 characters
    if len(text) > 250:
        text = text[:250]
        for punct in ['.', '!', '?']:
            if punct in text[-30:]:
                text = text[:text.rfind(punct)+1]
                break
        text = text.strip()

    return text

# --- Nutrition Data Fetcher ---
def get_food_data(query):
    url = "https://api.edamam.com/api/nutrition-data"
    params = {
        "app_id": EDAMAM_APP_ID,
        "app_key": EDAMAM_APP_KEY,
        "ingr": query
    }
    response = requests.get(url, params=params)
    return response.json() if response.status_code == 200 else None

# --- Chat Endpoint ---
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_input = data.get("message", "")
    print(f"📩 Received from Flutter: {user_input}")

    if not user_input:
        return jsonify({"reply": "Please ask something about food or nutrition!"}), 400

    try:
        # If input looks like a nutrition query
        if any(word in user_input.lower() for word in
               ["calorie", "nutrition", "fat", "protein", "carbs", "ingredient", "vitamin", "food"]):
            
            food_data = get_food_data(user_input)

            if food_data and "totalNutrients" in food_data:
                calories = food_data.get("calories", 0)
                protein = food_data["totalNutrients"].get("PROCNT", {}).get("quantity", 0)
                fat = food_data["totalNutrients"].get("FAT", {}).get("quantity", 0)
                carbs = food_data["totalNutrients"].get("CHOCDF", {}).get("quantity", 0)

                reply = (
                    f"🍛 {calories:.0f} kcal | "
                    f"Protein: {protein:.1f} g | "
                    f"Fat: {fat:.1f} g | "
                    f"Carbs: {carbs:.1f} g"
                )

            else:
                prompt = (
                    f"Answer clearly and briefly in 2–3 short lines only. "
                    f"No lists or long paragraphs. {user_input}"
                )
                reply = model.generate_content(prompt).text

        else:
            # Normal chatbot conversation
            prompt = (
                f"Answer this question concisely in 2–3 lines only. "
                f"No long paragraphs, no lists. Question: {user_input}"
            )
            reply = model.generate_content(prompt).text

    except Exception as e:
        print("⚠️ ERROR:", e)
        reply = "⚠️ Something went wrong. Please try again later."

    cleaned_reply = clean_response(reply)
    print(f"🤖 Reply to Flutter: {cleaned_reply}\n")

    return jsonify({"reply": cleaned_reply})

# --- Run Server ---
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))  # required for Render / Railway
    app.run(host="0.0.0.0", port=port)

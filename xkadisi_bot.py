# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import tweepy
import requests 
import time
import os
import logging
import sys
from datetime import datetime, timezone

# --- 1. WEB SUNUCUSU AYARLARI ---
app = Flask(__name__)
CORS(app) 

# --- LOGLAMA ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- KEY KONTROL ---
if not os.environ.get("GROK_API_KEY"):
    logger.error("❌ HATA: GROK_API_KEY eksik! Render ayarlarını kontrol edin.")

# --- TWITTER CLIENT BAŞLATMA ---
client = tweepy.Client(
    bearer_token=os.environ.get("BEARER_TOKEN"),
    consumer_key=os.environ.get("CONSUMER_KEY"),
    consumer_secret=os.environ.get("CONSUMER_SECRET"),
    access_token=os.environ.get("ACCESS_TOKEN"),
    access_token_secret=os.environ.get("ACCESS_TOKEN_SECRET"),
    wait_on_rate_limit=True
)

BOT_ID = 1997244309243060224
ANSWERED_TWEET_IDS = set()
BOT_USERNAME = "XKadisi" 

def get_bot_username():
    global BOT_USERNAME
    try:
        me = client.get_me()
        if me.data:
            BOT_USERNAME = me.data.username
            logger.info(f"✅ Bot Kimliği: @{BOT_USERNAME}")
    except: pass
    return BOT_USERNAME

# =====================================================
# BÖLÜM A: TWITTER FETVA (Grok-3)
# =====================================================
def get_fetva_twitter(soru, context=None):
    prompt_text = f"KULLANICI SORUSU: {soru}"
    if context: prompt_text += f"\n(BAĞLAM: '{context}')"

    system_prompt = """
    Sen "X Kadısı" isminde, Ehl-i Sünnet kaynaklarına (İbn Abidin, Nevevi) hakim bir Fıkıh Uzmanısın.
    GÖREVİN: Sorulan meseleyi fıkıh kitaplarından tara, mezheplerin detaylarını analiz et.
    
    --- FORMAT ---
    (Kısa giriş)
    🟦 HANEFİ: ... (Kaynak: ...)
    🟪 ŞAFİİ: ... (Kaynak: ...)
    🟩 MALİKİ: ... (Kaynak: ...)
    🟧 HANBELİ: ... (Kaynak: ...)
    ⚠️ SONUÇ: @abdulazizguven'e danışın.

    DİKKAT: Yemin Kefaretinde önce Doyurmak, yoksa Oruç gelir. Sıralamaya uy.
    """

    api_key = os.environ.get("GROK_API_KEY")
    if not api_key: return None

    try:
        # GROK-3 KULLANIYORUZ
        payload = {
            "model": "grok-3", # <-- GÜNCELLENDİ
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_text}
            ],
            "max_tokens": 1200,
            "temperature": 0.1
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        r = requests.post("https://api.x.ai/v1/chat/completions", json=payload, headers=headers, timeout=50)
        
        if r.status_code == 200:
            return r.json()['choices'][0]['message']['content'].strip()
        else:
            logger.error(f"❌ API HATASI (Twitter): {r.text}")
            return None

    except Exception as e:
        logger.error(f"Bağlantı Hatası: {e}")
        return None

# =====================================================
# BÖLÜM B: WEB SİTESİ FETVA (Grok-3)
# =====================================================
def get_fetva_web(soru):
    system_prompt = """
    KİMLİK: Sen "Fukaha Meclisi"nin yapay zeka asistanısın. 4 Hak Mezhebe hakimsin.
    
    MOD 1: SOHBET (Selam verilirse al).
    MOD 2: FIKIH (Detaylı, Kaynaklı, 4 Mezhepli cevap ver).

    FORMAT:
    "Selamun Aleyküm..."
    <br><br><b>📌 ÖZET HÜKÜM:</b><br>...
    <br><br><b>⚖️ MEZHEP GÖRÜŞLERİ:</b><br>
    <b>🟦 HANEFİ:</b> ... (Kaynak: ...)<br>
    <b>🟪 ŞAFİİ:</b> ... (Kaynak: ...)<br>
    <b>🟩 MALİKİ:</b> ... (Kaynak: ...)<br>
    <b>🟧 HANBELİ:</b> ... (Kaynak: ...)<br>
    <br><br><b>⚠️ SONUÇ VE TAVSİYE:</b><br>
    Kıymetli kardeşim, bu bilgiler genel fıkhi kaidelere dayanmaktadır. Durumunuzun özel detayları için lütfen sitemizdeki <b>"Soru Sor"</b> butonunu kullanarak fetva alınız.
    """

    api_key = os.environ.get("GROK_API_KEY")
    if not api_key: return "Sistem hatası: API Key bulunamadı."

    try:
        # GROK-3 KULLANIYORUZ
        payload = {
            "model": "grok-3", # <-- GÜNCELLENDİ
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": soru}
            ],
            "max_tokens": 2000,
            "temperature": 0.2
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        r = requests.post("https://api.x.ai/v1/chat/completions", json=payload, headers=headers, timeout=60)

        if r.status_code == 200:
            return r.json()['choices'][0]['message']['content']
        else:
            logger.error(f"❌ API HATASI (Web): {r.status_code} - {r.text}")
            return "Şu an teknik bir yoğunluk var, lütfen biraz sonra tekrar deneyiniz."

    except Exception as e:
        logger.error(f"❌ KRİTİK BAĞLANTI HATASI: {str(e)}")
        return "Bağlantı hatası oluştu."

# --- DÖNGÜLER VE ROUTES ---

def get_context(tweet):
    if not tweet.referenced_tweets: return None
    for ref in tweet.referenced_tweets:
        if ref.type in ['replied_to', 'quoted']:
            try:
                p = client.get_tweet(ref.id, tweet_fields=["text"])
                if p.data: return p.data.text
            except: pass
    return None

def twitter_loop_thread():
    global ANSWERED_TWEET_IDS, BOT_USERNAME
    logger.info("🚀 Twitter Modülü Başlatıldı...")
    BOT_USERNAME = get_bot_username()

    while True:
        try:
            query = f"@{BOT_USERNAME} -is:retweet -from:{BOT_USERNAME}"
            tweets = client.search_recent_tweets(
                query=query, max_results=20, 
                expansions=["referenced_tweets.id", "author_id"],
                tweet_fields=["text", "referenced_tweets", "created_at"]
            )
            if tweets.data:
                for t in reversed(tweets.data):
                    if str(t.id) in ANSWERED_TWEET_IDS: continue
                    
                    tweet_time = t.created_at
                    now = datetime.now(timezone.utc)
                    if (now - tweet_time).total_seconds() > 10800:
                        ANSWERED_TWEET_IDS.add(str(t.id)); continue

                    raw = t.text.lower().replace(f"@{BOT_USERNAME.lower()}", "").strip()
                    ctx = get_context(t) if len(raw) < 5 else None

                    logger.info(f"👁️ TWEET: {raw[:30]}...")
                    f = get_fetva_twitter(raw if raw else "Hüküm nedir?", ctx)
                    
                    if f:
                        client.create_tweet(text=f, in_reply_to_tweet_id=t.id)
                        logger.info(f"🚀 CEVAPLANDI: {t.id}")
                        ANSWERED_TWEET_IDS.add(str(t.id))
                        time.sleep(5)
        except Exception as e:
            logger.error(f"Döngü Hatası: {e}")
        time.sleep(200)

@app.route('/', methods=['GET'])
def home():
    return "X Kadısı & Fukaha Botu (Grok-3) Aktif! 🚀"

@app.route('/sor', methods=['POST'])
def sor():
    data = request.json
    soru = data.get('soru')
    if not soru: return jsonify({"cevap": "Soru yok"}), 400
    
    logger.info(f"🌍 WEB İSTEĞİ: {soru[:20]}...")
    cevap = get_fetva_web(soru)
    return jsonify({"cevap": cevap})

t = threading.Thread(target=twitter_loop_thread)
t.start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

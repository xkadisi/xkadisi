# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import tweepy
import requests  # <--- BU MUTLAKA OLMALI (OpenAI kütüphanesini sildik)
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
required_keys = ["BEARER_TOKEN", "CONSUMER_KEY", "CONSUMER_SECRET", "ACCESS_TOKEN", "ACCESS_TOKEN_SECRET", "GROK_API_KEY"]
if not all(os.environ.get(k) for k in required_keys):
    logger.error("❌ HATA: Keyler eksik! Render ayarlarını kontrol edin.")
    time.sleep(10)
    exit(1)

# --- AYARLAR ---
BOT_ID = 1997244309243060224  

# --- CLIENT BAŞLATMA ---
client = tweepy.Client(
    bearer_token=os.environ.get("BEARER_TOKEN"),
    consumer_key=os.environ.get("CONSUMER_KEY"),
    consumer_secret=os.environ.get("CONSUMER_SECRET"),
    access_token=os.environ.get("ACCESS_TOKEN"),
    access_token_secret=os.environ.get("ACCESS_TOKEN_SECRET"),
    wait_on_rate_limit=True
)


# --- HAFIZA ---
ANSWERED_TWEET_IDS = set()
BOT_USERNAME = None

def get_bot_username():
    global BOT_USERNAME
    try:
        me = client.get_me()
        if me.data:
            BOT_USERNAME = me.data.username
            logger.info(f"✅ Bot Kimliği: @{BOT_USERNAME}")
            return BOT_USERNAME
    except Exception:
        return "XKadisi"

# =====================================================
# BÖLÜM A: TWITTER FETVA MANTIĞI (KISA VE NET)
# =====================================================
def get_fetva_twitter(soru, context=None):
    prompt_text = f"KULLANICI SORUSU: {soru}"
    if context: prompt_text += f"\n(BAĞLAM: '{context}')"

    system_prompt = """
    Sen "X Kadısı" isminde, Ehl-i Sünnet kaynaklarına (İbn Abidin, Nevevi, İbn Kudame) hakim bir Fıkıh Uzmanısın.
    GÖREVİN: Sorulan meseleyi fıkıh kitaplarından tara, mezheplerin detaylarını analiz et ve görsel olarak şık bir formatta sun.
    
    --- GÖRSEL VE FORMAT KURALLARI ---
    1. ASLA "[Giriş Cümlesi]" yazma.
    2. Mezhep başlıklarını EMOJİLERLE ve BÜYÜK HARFLE yaz (🟦 HANEFİ, 🟪 ŞAFİİ, 🟩 MALİKİ, 🟧 HANBELİ).
    3. Kaynakları parantez içinde ekle.
    4. Yemin Kefareti vb. konularda TERTİP (Sıralama) esastır. Önce Doyurmak, yoksa Oruç.

    --- ÇIKTI ŞABLONU ---
    (Kısa giriş)
    🟦 HANEFİ: ... (Kaynak: ...)
    🟪 ŞAFİİ: ... (Kaynak: ...)
    🟩 MALİKİ: ... (Kaynak: ...)
    🟧 HANBELİ: ... (Kaynak: ...)
    ⚠️ SONUÇ: @abdulazizguven'e danışın.
    """

    api_key = os.environ.get("GROK_API_KEY")
    if not api_key: return None

    try:
        # DOĞRUDAN İSTEK (REQUESTS) YÖNTEMİ - KESİN ÇÖZÜM
        response = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "grok-2-1212", # En stabil model
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt_text}
                ],
                "max_tokens": 1200,
                "temperature": 0.1
            },
            timeout=45 # 45 Saniye bekle
        )
        
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content'].strip()
        else:
            logger.error(f"❌ API HATASI: {response.text}")
            return None

    except Exception as e:
        logger.error(f"Bağlantı Hatası: {e}")
        return None
# =====================================================
# BÖLÜM B: WEB SİTESİ FETVA MANTIĞI (SOHBET + FIKIH)
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
    <br><br><b>⚠️ SONUÇ:</b><br> Sitemizdeki "Soru Sor" butonunu kullanınız.
    """

    api_key = os.environ.get("GROK_API_KEY")
    if not api_key: return "API Anahtarı bulunamadı."

    try:
        # DOĞRUDAN İSTEK (REQUESTS) YÖNTEMİ
        response = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "grok-2-1212",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": soru}
                ],
                "max_tokens": 2000,
                "temperature": 0.2
            },
            timeout=60 # Web için 60 saniye
        )

        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            logger.error(f"❌ WEB API HATASI: {response.status_code} - {response.text}")
            return "Şu an teknik bir yoğunluk var, lütfen biraz sonra tekrar deneyiniz."

    except Exception as e:
        logger.error(f"❌ KRİTİK HATA (WEB): {str(e)}")
        return "Bağlantı hatası oluştu."
# =====================================================
# BÖLÜM C: TWITTER DÖNGÜSÜ
# =====================================================
def twitter_loop_thread():
    global ANSWERED_TWEET_IDS, BOT_USERNAME
    logger.info("🚀 Twitter Modülü (Thread) Başlatıldı...")
    BOT_USERNAME = get_bot_username()

    try:
        my_tweets = client.get_users_tweets(id=BOT_ID, max_results=50, tweet_fields=["referenced_tweets"])
        if my_tweets.data:
            for t in my_tweets.data:
                if t.referenced_tweets and t.referenced_tweets[0].type == 'replied_to':
                    ANSWERED_TWEET_IDS.add(str(t.referenced_tweets[0].id))
    except: pass

    while True:
        try:
            query = f"@{BOT_USERNAME} -is:retweet -from:{BOT_USERNAME}"
            tweets = client.search_recent_tweets(
                query=query, max_results=50, 
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
                    ctx = None
                    if len(raw) < 5:
                        ctx = get_context(t)
                        if not ctx and not raw:
                            ANSWERED_TWEET_IDS.add(str(t.id)); continue

                    logger.info(f"👁️ TWEET İŞLENİYOR: {raw[:30]}...")
                    f = get_fetva_twitter(raw if raw else "Hüküm nedir?", ctx)
                    if f:
                        try:
                            client.create_tweet(text=f, in_reply_to_tweet_id=t.id)
                            logger.info(f"🚀 CEVAPLANDI! {t.id}")
                            ANSWERED_TWEET_IDS.add(str(t.id))
                            time.sleep(5) 
                        except Exception as e:
                            logger.error(f"Tweet Gönderme Hatası: {e}")
                            ANSWERED_TWEET_IDS.add(str(t.id))
        except Exception as e:
            logger.error(f"Döngü Hatası: {e}")
        time.sleep(200)

# =====================================================
# BÖLÜM D: WEB VE BAŞLATMA
# =====================================================
@app.route('/', methods=['GET'])
def home():
    return "X Kadısı & Fukaha Botu Aktif! 🚀"

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

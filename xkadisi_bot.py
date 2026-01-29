# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import tweepy
from openai import OpenAI
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

grok_client = OpenAI(
    api_key=os.environ.get("GROK_API_KEY"),
    base_url="https://api.x.ai/v1"
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
# BÖLÜM A: TWITTER FETVA MANTIĞI (ESKİ SİSTEM - KATI VE KISA)
# =====================================================
def get_fetva_twitter(soru, context=None):
    prompt_text = f"KULLANICI SORUSU: {soru}"
    if context: prompt_text += f"\n(SORUNUN BAĞLAMI/ALINTILANAN TWEET: '{context}')"

    system_prompt = """
    Sen "X Kadısı" isminde, Fıkıh uzmanı bir botsun.
    
    GÖREVİN:
    Gelen soruyu analiz et ve sadece o soruya cevap ver.
    
    --- ANAYASA (SADECE VE SADECE KONU EŞLEŞİRSE KULLAN) ---
    Eğer soru aşağıdaki konulardan biriyle ilgiliyse, MUTLAKA bu şablonu kullan. 
    EĞER SORU BAŞKA BİR KONUYSA (Örn: Faiz, Namaz, Oruç) BU MADDELERİ YOK SAY VE SORUYU CEVAPLA.

    1. [KONU: KADINA DOKUNMAK İSE]
       - HANEFİ: Ten tene değmek abdesti ASLA BOZMAZ.
       - ŞAFİİ: Namahrem kadına ten tene değmek abdesti KESİN BOZAR.

    2. [KONU: KAN AKMASI İSE]
       - HANEFİ: Kan akarsa abdest BOZULUR.
       - ŞAFİİ: Ön/arka mahal hariç kan akması abdesti BOZMAZ.
    
    3. [KONU: KUSMAK İSE]
       - HANEFİ: Ağız dolusu kusmak bozar.
       - ŞAFİİ: Kusmak abdesti bozmaz.

    --- FORMAT KURALLARI ---
    1. Soru "Faiz, Banka, Pos Cihazı" gibiyse, Anayasayı boşver, o konunun fıkhi hükmünü ver.
    2. Kısa, net ve Twitter limitine uygun yaz.
    3. Mezhep farkı varsa belirt yoksa "Cumhura göre/Dört mezhebe göre" de.
    4. SONUÇ: "⚠️ Detay için hocalarımıza danışın."
    """

    try:
        r = grok_client.chat.completions.create(
            model="grok-3", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_text}
            ],
            max_tokens=600, 
            temperature=0.1 # Sıfırı 0.1 yaptık ki soruyu analiz etsin, ezberi bıraksın.
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Grok Hatası: {e}")
        return None

# =====================================================
# BÖLÜM B: WEB SİTESİ FETVA MANTIĞI (YENİ SİSTEM - DETAYLI VE HOCA)
# =====================================================
def get_fetva_web(soru):
    # YENİ DETAYLI PROMPT (Web sitesi için özel)
    system_prompt = """
    KİMLİK:
    Sen "Fukaha Meclisi"nin yapay zeka asistanısın. Ehl-i Sünnet ve'l Cemaat çizgisinde, Hanefi ve Şafii fıkhına hakim, ilmi derinliği olan, nazik bir fıkıh alimisin.

    GÖREVİN:
    Kullanıcının sorusunu geçiştirmeden; Ayet, Hadis ve Fıkıh kaidelerine dayanarak DETAYLICA cevaplamaktır.

    --- ANAYASA (BU KURALLARIN DIŞINA ASLA ÇIKMA) ---
    1. [KONU: KADINA DOKUNMAK]
       - HANEFİ: Ten tene değmek abdesti ASLA BOZMAZ.
       - ŞAFİİ: Namahrem kadına ten tene değmek abdesti KESİN BOZAR.
    2. [KONU: KAN AKMASI]
       - HANEFİ: Vücuttan kan akması abdesti BOZAR.
       - ŞAFİİ: Kan akması abdesti BOZMAZ.
    3. [KONU: KUSMAK]
       - HANEFİ: Ağız dolusu kusmak bozar.
       - ŞAFİİ: Kusmak abdesti bozmaz.

    CEVAPLAMA FORMATI (HTML ETİKETLERİ KULLAN):
    1. GİRİŞ: "Selamun Aleyküm kıymetli kardeşim," gibi sıcak bir giriş.
    2. NET HÜKÜM: Sorunun cevabını başta net ver.
    3. DELİLLER VE İZAH: Konuyu detaylandır. "Efendimiz (s.a.v) şöyle buyurmuştur..." diyerek ilmi izah yap.
    4. MEZHEP FARKLARI: Hanefi ve Şafii arasındaki farkı mutlaka <b>Hanefi:</b> ve <b>Şafii:</b> şeklinde ayır.
    5. SONUÇ VE DUA: Dua ile bitir.

    ÜSLUP:
    - Robot gibi değil, bir insan gibi sıcak konuş.
    - Kısa cevap verme, konuyu etraflıca anlat.
    """
    try:
        r = grok_client.chat.completions.create(
            model="grok-3", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": soru}
            ],
            max_tokens=2000, # <--- Uzun cevap için limit artırıldı
            temperature=0.1  # <--- Biraz daha akıcı konuşması için
        )
        return r.choices[0].message.content
    except Exception as e:
        return "Şu an kaynaklara ulaşmakta güçlük çekiyorum."

# =====================================================
# BÖLÜM C: TWITTER DÖNGÜSÜ (THREAD)
# =====================================================
def twitter_loop_thread():
    global ANSWERED_TWEET_IDS, BOT_USERNAME
    logger.info("🚀 Twitter Modülü (Thread) Başlatıldı...")
    
    BOT_USERNAME = get_bot_username()

    # Geçmişi Tara
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
                    
                    # BURADA ESKİ KATI FONKSİYONU ÇAĞIRIYORUZ
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
# BÖLÜM D: WEB YOLLARI (ROUTES)
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
    
    # BURADA YENİ DETAYLI FONKSİYONU ÇAĞIRIYORUZ
    cevap = get_fetva_web(soru)
    return jsonify({"cevap": cevap})

# =====================================================
# BÖLÜM E: BAŞLATMA (ENTRY POINT)
# =====================================================
t = threading.Thread(target=twitter_loop_thread)
t.start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# -*- coding: utf-8 -*-
import tweepy
from openai import OpenAI
import time
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Key'ler
BEARER_TOKEN = os.environ.get("BEARER_TOKEN")
CONSUMER_KEY = os.environ.get("CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("CONSUMER_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")
GROK_API_KEY = os.environ.get("GROK_API_KEY")

# --- BURAYI DEĞİŞTİRİN ---
# Botun Numeric ID'sini buraya tırnaksız (sayı olarak) yazın.
# TweeterID.com gibi sitelerden öğrenebilirsiniz.
BOT_ID = 1871234567890123456  # <-- BURAYA GERÇEK ID'Yİ YAPIŞTIRIN

if not all([BEARER_TOKEN, CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, GROK_API_KEY]):
    logger.error("Eksik API key!")
    exit(1)

client = tweepy.Client(
    bearer_token=BEARER_TOKEN,
    consumer_key=CONSUMER_KEY,
    consumer_secret=CONSUMER_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET,
    wait_on_rate_limit=False 
)

grok_client = OpenAI(
    api_key=GROK_API_KEY,
    base_url="https://api.x.ai/v1"
)

# Global değişken
LAST_SEEN_ID = None 

# (get_bot_id fonksiyonunu sildik, gerek kalmadı)

def get_fetva(soru):
    prompt = f"""
Kullanıcı sorusu: {soru}
Dört büyük Sünni mezhebine göre detaylı fetva ver.
Her mezhep için hüküm ve kısa kaynak belirt.
Format:
Hanefi: [hüküm] (el-Hidâye)
Şafiî: [hüküm] (el-Mecmû')
Mâlikî: [hüküm] (Muvatta)
Hanbelî: [hüküm] (el-Muğnî)
Bu genel bilgilendirmedir, mutlak fetva değildir. Lütfen @abdulazizguven'e danışın.
Tüm cevap Türkçe olsun ve 280 karaktere sığmaya çalışsın.
"""
    try:
        response = grok_client.chat.completions.create(
            model="grok-beta", 
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Grok Hatası: {e}")
        return "Şu an kaynaklara erişilemiyor."

def cevap_ver():
    global LAST_SEEN_ID
    logger.info("Mention kontrol ediliyor...")
    
    try:
        # BOT_ID artık yukarıda elle tanımlı, API'ye sormuyoruz.
        mentions = client.get_users_mentions(
            id=BOT_ID,
            since_id=LAST_SEEN_ID, 
            max_results=5, 
            tweet_fields=["author_id", "conversation_id"]
        )
    except tweepy.TooManyRequests as e:
        reset_time = int(e.response.headers.get('x-rate-limit-reset', time.time() + 900))
        wait_seconds = max(reset_time - int(time.time()) + 10, 60)
        logger.warning(f"⚠️ RATE LIMIT (Mention Okuma)! {wait_seconds} saniye bekleniyor...")
        time.sleep(wait_seconds)
        return
    except Exception as e:
        logger.error(f"Hata: {e}")
        time.sleep(60)
        return

    if not mentions.data:
        logger.info("Yeni mention yok.")
        return

    for mention in reversed(mentions.data):
        LAST_SEEN_ID = mention.id
        
        soru = mention.text.lower().replace("@xkadisi", "").strip()
        if not soru:
            continue

        logger.info(f"Soru işleniyor: {soru}")
        fetva_metni = get_fetva(soru)
        cevap = f"Merhaba!\n\n{fetva_metni}"[:280]

        try:
            client.create_tweet(text=cevap, in_reply_to_tweet_id=mention.id)
            logger.info(f"Cevap gönderildi! ID: {mention.id}")
            time.sleep(5) 
        except Exception as e:
            logger.error(f"Tweet atma hatası: {e}")

logger.info("XKadisi botu (Hardcoded ID ile) başlatıldı...")
# İlk açılışta API sorgusu yapmadığımız için 429 yemeyeceğiz.

while True:
    cevap_ver()
    time.sleep(60)

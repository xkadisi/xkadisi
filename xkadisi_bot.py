# -*- coding: utf-8 -*-

import tweepy
from openai import OpenAI
import time
import os
import logging

# Loglama ayarları
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- YAPILANDIRMA ---
# Verdiğiniz ID buraya sabitlendi.
BOT_ID = 1997244309243060224 

# Key'ler
BEARER_TOKEN = os.environ.get("BEARER_TOKEN")
CONSUMER_KEY = os.environ.get("CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("CONSUMER_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")
GROK_API_KEY = os.environ.get("GROK_API_KEY")

if not all([BEARER_TOKEN, CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, GROK_API_KEY]):
    logger.error("Eksik API key! Lütfen çevre değişkenlerini (Environment Variables) kontrol edin.")
    exit(1)

# X Client Başlatma (Rate Limit kontrolünü elle yapacağız)
client = tweepy.Client(
    bearer_token=BEARER_TOKEN,
    consumer_key=CONSUMER_KEY,
    consumer_secret=CONSUMER_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET,
    wait_on_rate_limit=False 
)

# Grok Client Başlatma
grok_client = OpenAI(
    api_key=GROK_API_KEY,
    base_url="https://api.x.ai/v1"
)

# Global değişkenler
LAST_SEEN_ID = None  # En son işlenen tweet ID'si

def get_fetva(soru):
    """Grok üzerinden fetva üretir."""
    prompt = f"""
Kullanıcı sorusu: {soru}

Dört büyük Sünni mezhebine göre detaylı fetva ver.
Her mezhep için hüküm ve kısa kaynak belirt.

Format:
Hanefi: [hüküm] (el-Hidâye)
Şafiî: [hüküm] (el-Mecmû')
Mâlikî: [hüküm] (Muvatta)
Hanbelî: [hüküm] (el-Muğnî)

Bu genel bilgilendirmedir, mutlak fetva değildir. Lütfen ehline danışın.
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
    logger.info(f"Mention kontrol ediliyor... (ID: {BOT_ID})")
    
    try:
        # API ÇAĞRISI
        mentions = client.get_users_mentions(
            id=BOT_ID,
            since_id=LAST_SEEN_ID, 
            max_results=5, # Limit tasarrufu için az çekiyoruz
            tweet_fields=["author_id", "conversation_id", "created_at"]
        )
    except tweepy.TooManyRequests as e:
        reset_time = int(e.response.headers.get('x-rate-limit-reset', time.time() + 900))
        wait_seconds = max(reset_time - int(time.time()) + 10, 60)
        logger.warning(f"⚠️ RATE LIMIT (Mention Okuma)! {wait_seconds} saniye bekleniyor...")
        time.sleep(wait_seconds)
        return
    except Exception as e:
        logger.error(f"Mention çekme hatası: {e}")
        time.sleep(60)
        return

    if not mentions.data:
        logger.info("Yeni mention yok.")
        return

    # Mentionları eskiden yeniye doğru işle
    for mention in reversed(mentions.data):
        LAST_SEEN_ID = mention.id # Son işlenen ID'yi güncelle
        
        soru = mention.text.lower().replace("@xkadisi", "").strip()
        
        # Boş mention ise atla
        if not soru:
            logger.info(f"Boş mention atlandı: {mention.id}")
            continue

        logger.info(f"Soru işleniyor: {soru} (Gönderen: {mention.author_id})")
        fetva_metni = get_fetva(soru)
        
        # Cevabı hazırla (Limit 280 karakter)
        cevap = f"Merhaba!\n\n{fetva_metni}"[:280]

        try:
            client.create_tweet(text=cevap, in_reply_to_tweet_id=mention.id)
            logger.info(f"✅ Cevap gönderildi! Tweet ID: {mention.id}")
            time.sleep(5) # Seri cevaplarda spam'e düşmemek için bekleme
        except Exception as e:
            logger.error(f"Tweet atma hatası: {e}")

# --- ANA DÖNGÜ ---

logger.info(f"Bot başlatılıyor... Hedef ID: {BOT_ID}")
logger.info("API'ye 'get_me' sorgusu atılmayacak (Rate Limit Koruması Aktif).")

while True:
    cevap_ver()
    # Basic Tier limiti (15 dk'da 180 istek) için 60 sn bekleme güvenlidir.
    time.sleep(60)

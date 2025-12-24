# -*- coding: utf-8 -*-

import tweepy
from openai import OpenAI
import time
import os
import logging

# Loglama ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Key'ler
BEARER_TOKEN = os.environ.get("BEARER_TOKEN")
CONSUMER_KEY = os.environ.get("CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("CONSUMER_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")
GROK_API_KEY = os.environ.get("GROK_API_KEY")

if not all([BEARER_TOKEN, CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, GROK_API_KEY]):
    logger.error("Eksik API key! Çevre değişkenlerini kontrol edin.")
    exit(1)

# X Client Başlatma
client = tweepy.Client(
    bearer_token=BEARER_TOKEN,
    consumer_key=CONSUMER_KEY,
    consumer_secret=CONSUMER_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET,
    wait_on_rate_limit=False # Kontrolü biz yapacağız
)

# Grok Client Başlatma
grok_client = OpenAI(
    api_key=GROK_API_KEY,
    base_url="https://api.x.ai/v1"
)

# Global değişkenler
BOT_ID = None
LAST_SEEN_ID = None  # En son işlenen tweet ID'si (since_id için)

def get_bot_id():
    """Botun kendi ID'sini sadece bir kez çeker."""
    global BOT_ID
    try:
        me = client.get_me()
        BOT_ID = me.data.id
        logger.info(f"Bot ID alındı: {BOT_ID}")
    except Exception as e:
        logger.error(f"Bot ID alınamadı: {e}")
        exit(1)

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

Bu genel bilgilendirmedir, mutlak fetva değildir. Lütfen @abdulazizguven'e danışın.
Tüm cevap Türkçe olsun ve 280 karaktere sığmaya çalışsın veya thread yapısına uygun olsun.
"""
    try:
        response = grok_client.chat.completions.create(
            model="grok-beta", # Model ismi değişebilir, kontrol edin
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
        # API ÇAĞRISI OPTİMİZASYONU:
        # 1. user_id: Değişkenden alıyoruz (API çağrısı yapmıyoruz)
        # 2. since_id: Sadece son gördüğümüzden sonrasını istiyoruz.
        mentions = client.get_users_mentions(
            id=BOT_ID,
            since_id=LAST_SEEN_ID, 
            max_results=5, # Limit tasarrufu
            tweet_fields=["author_id", "conversation_id"]
        )
    except tweepy.TooManyRequests as e:
        # Rate limit headerlarını oku
        reset_time = int(e.response.headers.get('x-rate-limit-reset', time.time() + 900))
        wait_seconds = max(reset_time - int(time.time()) + 10, 60)
        logger.warning(f"⚠️ RATE LIMIT! {wait_seconds} saniye bekleniyor...")
        time.sleep(wait_seconds)
        return
    except Exception as e:
        logger.error(f"Mention çekme hatası: {e}")
        # Eğer hata "403 Forbidden" ise muhtemelen Free Tier'dasınızdır.
        if "403" in str(e) or "429" in str(e):
             logger.critical("HATA: Paketiniz Mention okumayı desteklemiyor olabilir (Free Tier sorunu).")
        time.sleep(300)
        return

    if not mentions.data:
        logger.info("Yeni mention yok.")
        return

    # Mentionları eskiden yeniye doğru işle
    for mention in reversed(mentions.data):
        LAST_SEEN_ID = mention.id # Son işlenen ID'yi güncelle
        
        soru = mention.text.lower().replace("@xkadisi", "").strip()
        if not soru:
            continue

        logger.info(f"Soru işleniyor: {soru}")
        fetva_metni = get_fetva(soru)
        
        # Cevabı parça parça gönderme (Tweet limitine takılmamak için basit kontrol)
        # Not: X API v2 karakter limiti 280'dir, uzun cevaplar için split gerekebilir.
        # Burada basitçe ilk kısmı gönderiyoruz.
        cevap = f"Merhaba!\n\n{fetva_metni}"[:280] 

        try:
            client.create_tweet(text=cevap, in_reply_to_tweet_id=mention.id)
            logger.info(f"Cevap gönderildi! ID: {mention.id}")
            time.sleep(5) # Seri cevaplarda spam'e düşmemek için kısa bekleme
        except Exception as e:
            logger.error(f"Tweet atma hatası: {e}")

# --- ANA DÖNGÜ ---

logger.info("Bot başlatılıyor...")
get_bot_id() # ID'yi başta bir kez al

logger.info("XKadisi botu dinlemede...")
while True:
    cevap_ver()
    # Basic Tier için 15 dakikada 180 istek hakkı vardır.
    # 60 saniyede bir kontrol güvenlidir.
    time.sleep(60)

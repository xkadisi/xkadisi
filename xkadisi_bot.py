# -*- coding: utf-8 -*-
import tweepy
from openai import OpenAI
import time
import os
import logging
import sys

# Loglama ayarları (Hem dosyaya hem konsola basması için)
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# --- DEBUG BAŞLANGIÇ ---
print("--- BAŞLATILIYOR: Değişken Kontrolü ---")
# Değişkenleri al
BEARER_TOKEN = os.environ.get("BEARER_TOKEN")
CONSUMER_KEY = os.environ.get("CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("CONSUMER_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")
GROK_API_KEY = os.environ.get("GROK_API_KEY")

# Hangi anahtar eksikse ekrana yazdır (Güvenlik için değerleri gizliyoruz)
missing_keys = []
if not BEARER_TOKEN: missing_keys.append("BEARER_TOKEN")
if not CONSUMER_KEY: missing_keys.append("CONSUMER_KEY")
if not CONSUMER_SECRET: missing_keys.append("CONSUMER_SECRET")
if not ACCESS_TOKEN: missing_keys.append("ACCESS_TOKEN")
if not ACCESS_TOKEN_SECRET: missing_keys.append("ACCESS_TOKEN_SECRET")
if not GROK_API_KEY: missing_keys.append("GROK_API_KEY")

if missing_keys:
    print("❌ KRİTİK HATA: Aşağıdaki Environment Variable'lar EKSİK veya OKUNAMIYOR:")
    for key in missing_keys:
        print(f"- {key}")
    print("Lütfen paneldeki değerlerin başında/sonunda boşluk olmadığından emin olun.")
    # Programın çökme sebebini görmek için çıkış yapıyoruz
    exit(1)
else:
    print("✅ Tüm anahtarlar başarıyla okundu.")

# --- YAPILANDIRMA ---
BOT_ID = 1997244309243060224  # Sizin botunuzun ID'si

# X Client Başlatma
try:
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
except Exception as e:
    print(f"❌ Client başlatma hatası: {e}")
    exit(1)

# Global değişkenler
LAST_SEEN_ID = None 

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
            model="grok-3",  # <-- GÜNCELLENDİ: grok-beta yerine grok-3
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Grok Hatası: {e}")
        return f"Şu an sistemsel bir yoğunluk var. (Kod: {int(time.time())})"

def cevap_ver():
    global LAST_SEEN_ID
    logger.info(f"Mention kontrol ediliyor... (ID: {BOT_ID})")
    
    try:
        mentions = client.get_users_mentions(
            id=BOT_ID,
            since_id=LAST_SEEN_ID, 
            max_results=5, 
            tweet_fields=["author_id", "created_at"]
        )
    except tweepy.TooManyRequests as e:
        reset_time = int(e.response.headers.get('x-rate-limit-reset', time.time() + 900))
        wait_seconds = max(reset_time - int(time.time()) + 10, 60)
        logger.warning(f"⚠️ RATE LIMIT! {wait_seconds} saniye bekleniyor...")
        time.sleep(wait_seconds)
        return
    except Exception as e:
        logger.error(f"Mention hatası: {e}")
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
            logger.info(f"✅ Cevap gönderildi! ID: {mention.id}")
            time.sleep(5) 
        except Exception as e:
            logger.error(f"Tweet atma hatası: {e}")

# --- ANA DÖNGÜ ---
print("✅ Bot başarıyla başlatıldı, döngüye giriliyor...")
while True:
    cevap_ver()
    time.sleep(60)

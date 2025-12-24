# -*- coding: utf-8 -*-
import tweepy
from openai import OpenAI
import time
import os
import logging
import sys

# Loglama ayarları
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- AYARLAR ---
BOT_ID = 1997244309243060224  # Sizin botunuzun ID'si

# Environment Variables
BEARER_TOKEN = os.environ.get("BEARER_TOKEN")
CONSUMER_KEY = os.environ.get("CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("CONSUMER_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")
GROK_API_KEY = os.environ.get("GROK_API_KEY")

# Key Kontrolü
if not all([BEARER_TOKEN, CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, GROK_API_KEY]):
    print("❌ EKSİK KEY HATASI: Lütfen Environment Variables kontrol edin.")
    exit(1)

# Client Başlatma
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

LAST_SEEN_ID = None 

def get_fetva(soru):
    """Grok üzerinden detaylı ve delilli fetva üretir."""
    prompt = f"""
Kullanıcı sorusu: {soru}

Dört büyük Sünni mezhebine göre bu konunun hükmünü detaylı ve anlaşılır bir şekilde açıkla.
Cevapların kısa olmasın, konuyu doyurucu bir şekilde izah et.
Her mezhep için hükmü belirttikten sonra, parantez içinde mutlaka dayandığı delili veya fıkıh kitabını yaz.

Lütfen tam olarak aşağıdaki formatı kullan:

Hanefi: [Hüküm ve detaylı açıklama] (Kaynak: el-Hidâye)
\n
Şafiî: [Hüküm ve detaylı açıklama] (Kaynak: el-Mecmû')
\n
Mâlikî: [Hüküm ve detaylı açıklama] (Kaynak: Muvatta)
\n
Hanbelî: [Hüküm ve detaylı açıklama] (Kaynak: el-Muğnî)

Sadece bu bilgileri ver, giriş veya bitiş cümlesi yazma.
"""
    try:
        response = grok_client.chat.completions.create(
            model="grok-3", 
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000, # Uzun cevap için token limitini artırdık
            temperature=0.4
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Grok Hatası: {e}")
        return None

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
        logger.warning("⚠️ Rate limit! Bekleniyor...")
        time.sleep(60)
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
        
        # 1. Fetvayı al
        fetva_metni = get_fetva(soru)
        
        if not fetva_metni:
            continue

        # 2. Metni birleştir (Giriş + Fetva + Yasal Uyarı)
        # Karakter sınırı olmadığı için hepsini tek string yapıyoruz.
        tam_cevap = (
            f"Merhaba!\n\n"
            f"{fetva_metni}\n\n"
            f"⚠️ Bu genel bilgilendirmedir, mutlak fetva değildir. Lütfen @abdulazizguven'e danışın."
        )

        try:
            # Tek seferde gönderiyoruz (Premium hesaplar için)
            client.create_tweet(text=tam_cevap, in_reply_to_tweet_id=mention.id)
            logger.info(f"✅ Uzun cevap gönderildi! ID: {mention.id}")
            time.sleep(5) 
        except Exception as e:
            logger.error(f"Tweet atma hatası: {e}")
            # Eğer hesap Premium değilse burada 'text is too long' hatası verir.

# --- ANA DÖNGÜ ---
print("✅ Bot (Long Tweet Modu) başlatıldı...")
while True:
    cevap_ver()
    time.sleep(60)

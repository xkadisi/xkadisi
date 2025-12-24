# -*- coding: utf-8 -*-
import tweepy
from openai import OpenAI
import time
import os
import logging
import sys

# --- LOGLAMA AYARLARI ---
# Hem sunucu loglarına (Render) hem de ekrana basması için
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- AYARLAR ---
# ID'niz sabitlendi
BOT_ID = 1997244309243060224  

# Environment Variables (Render'dan okur)
BEARER_TOKEN = os.environ.get("BEARER_TOKEN")
CONSUMER_KEY = os.environ.get("CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("CONSUMER_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")
GROK_API_KEY = os.environ.get("GROK_API_KEY")

# Key Kontrolü
if not all([BEARER_TOKEN, CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, GROK_API_KEY]):
    print("❌ EKSİK KEY HATASI: Lütfen Render panelinden Environment Variables kontrol edin.")
    # Kritik hata ama logu görebilmek için hemen kapatmıyoruz, bekletiyoruz.
    time.sleep(10)
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

# Render her yeniden başladığında hafıza sıfırlanır.
# Bu yüzden ilk açılışta son mentionları tekrar cevaplamaması için bir kontrol mekanizması ekleyebiliriz
# ama şimdilik "görmeme" sorununu çözmek için hafızasız başlatıyoruz.
LAST_SEEN_ID = None 

def get_fetva(soru):
    """Grok-3 ile detaylı ve kaynaklı fetva üretir."""
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
            model="grok-3", # <-- GÜNCEL MODEL
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000, 
            temperature=0.4
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Grok Hatası: {e}")
        return None

def cevap_ver():
    global LAST_SEEN_ID
    logger.info(f"🔍 Mentionlar kontrol ediliyor... (Bot ID: {BOT_ID})")
    
    try:
        # since_id yoksa (ilk başlangıçsa) en son 10 mention'ı çeker.
        # since_id varsa, sadece yeni gelenleri çeker.
        mentions = client.get_users_mentions(
            id=BOT_ID,
            since_id=LAST_SEEN_ID, 
            max_results=10, 
            tweet_fields=["author_id", "created_at", "text"]
        )
    except tweepy.TooManyRequests as e:
        logger.warning("⚠️ Rate limit! 60 saniye bekleniyor...")
        time.sleep(60)
        return
    except Exception as e:
        logger.error(f"Mention çekme hatası: {e}")
        time.sleep(60)
        return

    if not mentions.data:
        logger.info("📭 Yeni mention yok. (Kutu boş veya filtrelenmiş)")
        return

    # Mention bulunduysa loga yazalım
    logger.info(f"✅ {len(mentions.data)} adet mention yakalandı!")

    for mention in reversed(mentions.data):
        LAST_SEEN_ID = mention.id
        
        # Kendi tweetlerimizi cevaplamayalım (sonsuz döngü koruması)
        if str(mention.author_id) == str(BOT_ID):
            continue

        soru = mention.text.lower().replace("@xkadisi", "").strip()
        
        # Loga soruyu basalım ki gördüğünden emin olalım
        logger.info(f"📩 İŞLENİYOR: {mention.text} (Gönderen: {mention.author_id})")

        if not soru:
            logger.info("❌ Boş mention, geçiliyor.")
            continue

        # Fetva al
        fetva_metni = get_fetva(soru)
        
        if not fetva_metni:
            logger.error("❌ Fetva üretilemedi, pas geçiliyor.")
            continue

        # Tek parça uzun cevap oluştur
        tam_cevap = (
            f"Merhaba!\n\n"
            f"{fetva_metni}\n\n"
            f"⚠️ Bu genel bilgilendirmedir, mutlak fetva değildir. Lütfen @abdulazizguven'e danışın."
        )

        try:
            # Long Tweet Gönderimi
            client.create_tweet(text=tam_cevap, in_reply_to_tweet_id=mention.id)
            logger.info(f"🚀 CEVAP GÖNDERİLDİ! Tweet ID: {mention.id}")
            time.sleep(10) # Spam koruması için bekleme
        except Exception as e:
            logger.error(f"❌ Tweet atma hatası: {e}")
            if "duplicate" in str(e).lower():
                logger.info("💡 Bu tweet daha önce cevaplanmış.")

# --- ANA DÖNGÜ ---
print("✅ Bot başlatıldı (Render Mode)")
print("✅ Özellikler: Long Tweet, Grok-3, Hardcoded ID")

while True:
    cevap_ver()
    # Basic Tier için güvenli bekleme süresi
    time.sleep(60)

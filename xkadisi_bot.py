# -*- coding: utf-8 -*-
import tweepy
from openai import OpenAI
import time
import os
import logging
import sys

# --- LOGLAMA AYARLARI ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- YAPILANDIRMA ---
BOT_ID = 1997244309243060224  # Botunuzun ID'si

# Environment Variables
BEARER_TOKEN = os.environ.get("BEARER_TOKEN")
CONSUMER_KEY = os.environ.get("CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("CONSUMER_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")
GROK_API_KEY = os.environ.get("GROK_API_KEY")

# Key Kontrolü
if not all([BEARER_TOKEN, CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, GROK_API_KEY]):
    print("❌ EKSİK KEY HATASI: Environment Variables kontrol edin.")
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

# Global değişken
LAST_SEEN_ID = None 

def get_fetva(soru):
    """Grok-3 ile detaylı fetva üretir."""
    prompt = f"""
Kullanıcı sorusu: {soru}

Dört büyük Sünni mezhebine göre bu konunun hükmünü detaylı ve anlaşılır bir şekilde açıkla.
Cevapların kısa olmasın, konuyu doyurucu bir şekilde izah et.
Her mezhep için hükmü belirttikten sonra, parantez içinde mutlaka dayandığı delili veya fıkıh kitabını yaz.

Format:
Hanefi: [Hüküm] (Kaynak: el-Hidâye)
Şafiî: [Hüküm] (Kaynak: el-Mecmû')
Mâlikî: [Hüküm] (Kaynak: Muvatta)
Hanbelî: [Hüküm] (Kaynak: el-Muğnî)

Giriş veya bitiş cümlesi yazma, sadece yukarıdaki formatı ver.
"""
    try:
        response = grok_client.chat.completions.create(
            model="grok-3",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000, 
            temperature=0.4
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Grok Hatası: {e}")
        return None

def get_replied_ids():
    """Daha önce cevap verilmiş tweetleri hafızaya alır (Spam önleme)."""
    replied_ids = set()
    try:
        # Botun kendi timeline'ına bakarak kime cevap verdiğini bulur
        # Bu yöntem, takipleşme olmasa bile botun cevaplarını görür.
        my_tweets = client.get_users_tweets(
            id=BOT_ID,
            max_results=50, # Son 50 cevabı kontrol et
            tweet_fields=["referenced_tweets"]
        )
        if my_tweets.data:
            for tweet in my_tweets.data:
                if tweet.referenced_tweets:
                    for ref in tweet.referenced_tweets:
                        if ref.type == 'replied_to':
                            replied_ids.add(str(ref.id))
    except Exception as e:
        logger.error(f"Geçmiş kontrol hatası: {e}")
    return replied_ids

def process_mention(mention):
    """Mention'ı işler ve cevaplar (Herkese Açık)."""
    soru = mention.text.lower().replace("@xkadisi", "").strip()
    logger.info(f"📩 İŞLENİYOR: {mention.text} (Yazar ID: {mention.author_id})")

    if not soru:
        return

    fetva_metni = get_fetva(soru)
    if not fetva_metni:
        return

    # Cevap Metni
    tam_cevap = (
        f"Merhaba!\n\n"
        f"{fetva_metni}\n\n"
        f"⚠️ Bu genel bilgilendirmedir, mutlak fetva değildir. Lütfen @abdulazizguven'e danışın."
    )

    try:
        # in_reply_to_tweet_id parametresi, mention atan kişiyi otomatik etiketler.
        # Takipleşme olup olmaması önemli değildir.
        client.create_tweet(text=tam_cevap, in_reply_to_tweet_id=mention.id)
        logger.info(f"🚀 CEVAP GÖNDERİLDİ! Tweet ID: {mention.id}")
        time.sleep(10) 
    except Exception as e:
        logger.error(f"Tweet atma hatası: {e}")

def main_loop():
    """Ana döngü: Hem eksikleri tamamlar hem yenileri dinler."""
    global LAST_SEEN_ID
    
    # 1. Adım: Zaten cevapladıklarımızı öğren
    answered_ids = get_replied_ids()
    
    logger.info(f"🔄 Mentionlar taranıyor... (Ref ID: {LAST_SEEN_ID})")
    
    try:
        # Takip durumu fark etmeksizin mentionları çeker
        mentions = client.get_users_mentions(
            id=BOT_ID,
            since_id=LAST_SEEN_ID,
            max_results=10, 
            tweet_fields=["created_at", "text", "author_id"]
        )
    except Exception as e:
        logger.error(f"API Hatası: {e}")
        time.sleep(60)
        return

    if not mentions.data:
        # Mention yoksa bekle
        return

    logger.info(f"🔔 {len(mentions.data)} mention bulundu.")
    
    # Eskiden yeniye doğru işle
    for mention in reversed(mentions.data):
        LAST_SEEN_ID = mention.id
        
        # Kendimize cevap vermeyelim
        if str(mention.author_id) == str(BOT_ID):
            continue
            
        # Eğer bu tweet'e daha önce cevap VERMEMİŞSEK -> Cevapla
        if str(mention.id) not in answered_ids:
            process_mention(mention)
            # Cevapladığımız listesine ekleyelim ki döngü içinde tekrar cevaplamasın
            answered_ids.add(str(mention.id))
        else:
            logger.info(f"⏭️ Bu tweete zaten cevap verilmiş: {mention.id}")

# --- BAŞLATMA ---
print("✅ Bot Başlatıldı (Herkese Açık Mod)")
print("ℹ️ Not: X Ayarlarından 'Bildirim Filtreleri'nin kapalı olduğundan emin olun.")

while True:
    main_loop()
    time.sleep(60)

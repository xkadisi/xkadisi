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
BOT_ID = 1997244309243060224  

# Environment Variables
BEARER_TOKEN = os.environ.get("BEARER_TOKEN")
CONSUMER_KEY = os.environ.get("CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("CONSUMER_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")
GROK_API_KEY = os.environ.get("GROK_API_KEY")

if not all([BEARER_TOKEN, CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, GROK_API_KEY]):
    print("❌ EKSİK KEY HATASI.")
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

LAST_SEEN_ID = None 

def get_fetva(soru):
    """Grok-3 ile detaylı fetva üretir."""
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
            max_tokens=2000, 
            temperature=0.4
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Grok Hatası: {e}")
        return None

def get_replied_ids():
    """Botun kendi attığı son tweetlere bakıp, kime cevap verdiğini (Referenced Tweets) bulur."""
    replied_ids = set()
    try:
        # Botun son 30 tweetini (cevaplarını) çek
        my_tweets = client.get_users_tweets(
            id=BOT_ID,
            max_results=30,
            tweet_fields=["referenced_tweets"]
        )
        if my_tweets.data:
            for tweet in my_tweets.data:
                if tweet.referenced_tweets:
                    for ref in tweet.referenced_tweets:
                        # Eğer bu tweet bir cevap (replied_to) ise, hedef ID'yi kaydet
                        if ref.type == 'replied_to':
                            replied_ids.add(str(ref.id))
    except Exception as e:
        logger.error(f"Geçmiş tweet kontrol hatası: {e}")
    
    return replied_ids

def process_mention(mention):
    """Bir mention'ı işleyip cevaplayan yardımcı fonksiyon."""
    soru = mention.text.lower().replace("@xkadisi", "").strip()
    logger.info(f"📩 İŞLENİYOR: {mention.text}")

    if not soru:
        return

    fetva_metni = get_fetva(soru)
    if not fetva_metni:
        return

    tam_cevap = (
        f"Merhaba!\n\n"
        f"{fetva_metni}\n\n"
        f"⚠️ Bu genel bilgilendirmedir, mutlak fetva değildir. Lütfen @abdulazizguven'e danışın."
    )

    try:
        client.create_tweet(text=tam_cevap, in_reply_to_tweet_id=mention.id)
        logger.info(f"🚀 CEVAP GÖNDERİLDİ! Tweet ID: {mention.id}")
        time.sleep(10) # Spam koruması
    except Exception as e:
        logger.error(f"Tweet atma hatası: {e}")

def startup_check():
    """Bot açılırken yapılan 'Eksik Tamamlama' kontrolü."""
    global LAST_SEEN_ID
    logger.info("🕵️ BAŞLANGIÇ KONTROLÜ: Cevaplanmamış eski tweetler taranıyor...")

    # 1. Adım: Hangi tweetlere zaten cevap verdik?
    answered_ids = get_replied_ids()
    logger.info(f"📋 Kayıtlara göre son {len(answered_ids)} mention'a zaten cevap verilmiş.")

    try:
        # 2. Adım: Son gelen 10 mention'ı çek
        mentions = client.get_users_mentions(
            id=BOT_ID,
            max_results=10, 
            tweet_fields=["created_at", "text"]
        )
        
        if not mentions.data:
            logger.info("📭 Hiç mention yok.")
            return

        logger.info(f"🔎 Son {len(mentions.data)} mention inceleniyor...")
        
        # Eskiden yeniye doğru tara
        for mention in reversed(mentions.data):
            LAST_SEEN_ID = mention.id  # En son ID'yi her zaman güncelle (döngü için)
            
            # Kendi tweetimizi görmezden gel
            if str(mention.author_id) == str(BOT_ID):
                continue
                
            # EĞER bu mention ID'si cevapladıklarımız listesinde YOKSA -> CEVAPLA
            if str(mention.id) not in answered_ids:
                logger.info(f"💡 EKSİK BULUNDU! Cevaplanmamış tweet: {mention.id}")
                process_mention(mention)
            else:
                logger.info(f"⏭️ Bu mention zaten cevaplanmış, geçiliyor: {mention.id}")
                
    except Exception as e:
        logger.error(f"Startup hatası: {e}")

def main_loop():
    """Normal çalışma döngüsü (Sadece yenileri bekler)"""
    global LAST_SEEN_ID
    logger.info(f"🔄 CANLI MOD: Yeni mentionlar bekleniyor... (Ref: {LAST_SEEN_ID})")
    
    try:
        mentions = client.get_users_mentions(
            id=BOT_ID,
            since_id=LAST_SEEN_ID, # Sadece son gördüğümüzden sonrakiler
            max_results=10, 
            tweet_fields=["created_at", "text", "author_id"]
        )
    except Exception as e:
        logger.error(f"Döngü hatası: {e}")
        time.sleep(60)
        return

    if not mentions.data:
        return

    logger.info(f"🔔 {len(mentions.data)} YENİ mention geldi!")
    
    for mention in reversed(mentions.data):
        LAST_SEEN_ID = mention.id
        if str(mention.author_id) == str(BOT_ID): continue
        
        # Canlı modda gelen her şey yenidir, direkt cevapla
        process_mention(mention)

# --- ANA PROGRAM AKIŞI ---
print("✅ Bot Başlatıldı (Akıllı Telafi Modu)")

# 1. Önce eksikleri kapat
startup_check()

# 2. Sonra sonsuz döngüye gir
while True:
    main_loop()
    time.sleep(60)

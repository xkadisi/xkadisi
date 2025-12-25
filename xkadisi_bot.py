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

# --- KEY KONTROL ---
required_keys = ["BEARER_TOKEN", "CONSUMER_KEY", "CONSUMER_SECRET", "ACCESS_TOKEN", "ACCESS_TOKEN_SECRET", "GROK_API_KEY"]
if not all(os.environ.get(k) for k in required_keys):
    logger.error("❌ HATA: Bazı Keyler Eksik! Render ayarlarını kontrol edin.")
    time.sleep(10)
    exit(1)

# --- AYARLAR ---
BOT_ID = 1997244309243060224  

# Client Başlatma
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

# Global Hafızalar
ANSWERED_TWEET_IDS = set()
ANSWERED_DM_IDS = set() 
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

def get_fetva(soru, context=None):
    prompt_text = f"Soru: {soru}"
    if context: prompt_text += f"\n(Bağlam: '{context}')"

    prompt = f"""
{prompt_text}

Dört Büyük Sünni Mezhebe (Hanefi, Şafiî, Mâlikî, Hanbelî) göre fıkhi hükmü detaylı ve delilli açıkla.

Format:
Hanefi: [Hüküm] (Kaynak)
Şafiî: [Hüküm] (Kaynak)
Mâlikî: [Hüküm] (Kaynak)
Hanbelî: [Hüküm] (Kaynak)

Giriş/Bitiş cümlesi yazma.
"""
    try:
        r = grok_client.chat.completions.create(
            model="grok-3",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000, temperature=0.4
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Grok Hatası: {e}")
        return None

def get_context(tweet):
    if not tweet.referenced_tweets: return None
    for ref in tweet.referenced_tweets:
        if ref.type in ['replied_to', 'quoted']:
            try:
                p = client.get_tweet(ref.id, tweet_fields=["text"])
                if p.data: return p.data.text
            except: pass
    return None

# --- DM KONTROL FONKSİYONU ---
def check_dms():
    """DM Kutusunu kontrol eder ve cevaplar."""
    global ANSWERED_DM_IDS
    logger.info("📨 DM Kutusu kontrol ediliyor...")
    
    try:
        # Son DM olaylarını çek
        events = client.get_direct_message_events(max_results=15, event_types=["MessageCreate"])
        
        if not events.data:
            return

        for event in reversed(events.data):
            # DM ID'si hafızada mı?
            if str(event.id) in ANSWERED_DM_IDS:
                continue

            # Mesajın içeriği ve gönderen
            message_data = event.message_create['message_data']
            sender_id = event.message_create['sender_id']
            text = message_data['text']

            # Kendi attığımız mesajları okumayalım
            if str(sender_id) == str(BOT_ID):
                continue
            
            logger.info(f"📩 YENİ DM: {text[:30]}... (Kimden: {sender_id})")

            # Fetva Al
            fetva = get_fetva(text)
            if fetva:
                try:
                    cevap = f"Merhaba!\n\n{fetva}\n\n⚠️ Bu mesajdaki bilgilendirme genel niteliktedir. Lütfen @abdulazizguven'e danışın."
                    
                    # DM ile Cevap Gönder
                    client.create_direct_message(participant_id=sender_id, text=cevap)
                    logger.info(f"🚀 DM CEVAPLANDI! (Kime: {sender_id})")
                    
                    ANSWERED_DM_IDS.add(str(event.id))
                    time.sleep(5)
                except Exception as e:
                    logger.error(f"❌ DM Gönderme Hatası: {e}")
                    # Hata: 403 Forbidden alırsanız Keyleri yenilemeniz gerekir.
                    if "403" in str(e):
                        logger.error("⚠️ DİKKAT: Anahtarlarınızda DM yetkisi yok! Lütfen Developer Portal'dan 'Regenerate' yapın.")
                    ANSWERED_DM_IDS.add(str(event.id)) 

    except Exception as e:
        logger.error(f"DM Hatası: {e}")

def tweet_loop():
    """Tweet Arama Döngüsü"""
    global ANSWERED_TWEET_IDS
    query = f"@{BOT_USERNAME} -is:retweet -from:{BOT_USERNAME}"
    logger.info(f"🔎 Tweet Araması: '{query}'")
    
    try:
        tweets = client.search_recent_tweets(
            query=query, max_results=100, 
            expansions=["referenced_tweets.id", "author_id"],
            tweet_fields=["text", "referenced_tweets"]
        )
        if tweets.data:
            for t in reversed(tweets.data):
                if str(t.id) in ANSWERED_TWEET_IDS: continue
                
                raw = t.text.lower().replace(f"@{BOT_USERNAME.lower()}", "").strip()
                ctx = None
                if len(raw) < 5:
                    ctx = get_context(t)
                    if not ctx and not raw:
                        ANSWERED_TWEET_IDS.add(str(t.id))
                        continue
                
                q = raw if raw else "Bu durumun hükmü nedir?"
                f = get_fetva(q, ctx)
                if f:
                    try:
                        msg = f"Merhaba!\n\n{f}\n\n⚠️ Bu genel bilgilendirmedir. Lütfen @abdulazizguven'e danışın."
                        client.create_tweet(text=msg, in_reply_to_tweet_id=t.id)
                        logger.info(f"🚀 TWEET CEVAPLANDI! {t.id}")
                        ANSWERED_TWEET_IDS.add(str(t.id))
                        time.sleep(5)
                    except Exception as e:
                        logger.error(f"Tweet Hatası: {e}")
                        ANSWERED_TWEET_IDS.add(str(t.id))
    except Exception as e:
        logger.error(f"Arama Hatası: {e}")

# --- BAŞLATMA ---
print("✅ Bot Başlatıldı (Tweet + DM Modu)")
BOT_USERNAME = get_bot_username()

# Geçmiş tweetleri hafızaya al
try:
    my_tweets = client.get_users_tweets(id=BOT_ID, max_results=50, tweet_fields=["referenced_tweets"])
    if my_tweets.data:
        for t in my_tweets.data:
            if t.referenced_tweets and t.referenced_tweets[0].type == 'replied_to':
                ANSWERED_TWEET_IDS.add(str(t.referenced_tweets[0].id))
except: pass

while True:
    # 1. Tweetleri Kontrol Et
    tweet_loop()
    
    # 2. DM'leri Kontrol Et
    check_dms()
    
    # 3. Bekle (Her ikisi için ortak bekleme süresi)
    time.sleep(70)

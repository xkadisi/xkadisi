# -*- coding: utf-8 -*-
import tweepy
from openai import OpenAI
import time
import os
import logging
import sys
from datetime import datetime, timezone

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
    logger.error("❌ HATA: Keyler eksik! Render ayarlarını kontrol edin.")
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

# --- HAFIZA SİSTEMİ ---
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

# --- TWEET DÖNGÜSÜ ---
def tweet_loop():
    global ANSWERED_TWEET_IDS
    query = f"@{BOT_USERNAME} -is:retweet -from:{BOT_USERNAME}"
    logger.info(f"🔎 Tweet Araması: '{query}'")
    
    try:
        # max_results=50 gayet yeterli ve güvenlidir
        tweets = client.search_recent_tweets(
            query=query, max_results=50, 
            expansions=["referenced_tweets.id", "author_id"],
            tweet_fields=["text", "referenced_tweets", "created_at"]
        )
        if tweets.data:
            for t in reversed(tweets.data):
                if str(t.id) in ANSWERED_TWEET_IDS: continue
                
                # ZAMAN FİLTRESİ: 1 saatten eski tweetleri cevaplama (Bot kapalıyken gelen eskiler)
                tweet_time = t.created_at
                now = datetime.now(timezone.utc)
                if (now - tweet_time).total_seconds() > 3600:
                    ANSWERED_TWEET_IDS.add(str(t.id))
                    continue

                raw = t.text.lower().replace(f"@{BOT_USERNAME.lower()}", "").strip()
                ctx = None
                
                # Sadece etiketlemiş ama soru yazmamışsa, üstteki tweeti (context) al
                if len(raw) < 5:
                    ctx = get_context(t)
                    if not ctx and not raw:
                        # Hem kendi yazısı yok hem bağlam yok -> Pas geç
                        ANSWERED_TWEET_IDS.add(str(t.id))
                        continue
                
                logger.info(f"👁️ İŞLENİYOR: {raw[:30]}...")

                q = raw if raw else "Bu durumun hükmü nedir?"
                f = get_fetva(q, ctx)
                if f:
                    try:
                        msg = f"Merhaba!\n\n{f}\n\n⚠️ Bu genel bilgilendirmedir. Lütfen @abdulazizguven'e danışın."
                        client.create_tweet(text=msg, in_reply_to_tweet_id=t.id)
                        logger.info(f"🚀 CEVAPLANDI! {t.id}")
                        ANSWERED_TWEET_IDS.add(str(t.id))
                        time.sleep(5) # Ardışık tweet atarken kısa mola
                    except Exception as e:
                        logger.error(f"Tweet Gönderme Hatası: {e}")
                        ANSWERED_TWEET_IDS.add(str(t.id))
    except Exception as e:
        logger.error(f"Arama Hatası: {e}")

# --- BAŞLATMA ---
print("✅ Bot Başlatıldı (SADECE TWEET MODU - DM KAPALI)")
BOT_USERNAME = get_bot_username()

# Geçmiş tweetleri hafızaya al ki tekrar cevaplamasın
try:
    logger.info("📂 Geçmiş cevaplar taranıyor...")
    my_tweets = client.get_users_tweets(id=BOT_ID, max_results=50, tweet_fields=["referenced_tweets"])
    if my_tweets.data:
        for t in my_tweets.data:
            if t.referenced_tweets and t.referenced_tweets[0].type == 'replied_to':
                ANSWERED_TWEET_IDS.add(str(t.referenced_tweets[0].id))
except: pass

while True:
    tweet_loop()
    
    # 90 Saniye Bekleme (1.5 Dakika)
    # Sadece tweet aradığımız için bu süre limitlere takılmadan sonsuza kadar çalışır.
    time.sleep(90)

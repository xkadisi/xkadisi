# -*- coding: utf-8 -*-
import tweepy
from openai import OpenAI
import time
import os
import logging
import sys
from datetime import datetime, timezone

# --- LOGLAMA ---
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

# Grok Client
grok_client = OpenAI(
    api_key=os.environ.get("GROK_API_KEY"),
    base_url="https://api.x.ai/v1"
)

# --- HAFIZA ---
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

# --- GELİŞMİŞ FETVA FONKSİYONU ---
def get_fetva(soru, context=None):
    prompt_text = f"Soru: {soru}"
    if context: prompt_text += f"\n(Bağlam: '{context}')"

    # SIKI FIKIH TALİMATI
    system_prompt = """
Sen, Ehl-i Sünnet vel-Cemaat çizgisinde, dört mezhebin (Hanefi, Şafiî, Mâlikî, Hanbelî) fıkıh usulüne ve furuuna hakim, son derece hassas bir fıkıh asistanısın.

GÖREVİN:
Kullanıcının sorduğu dini sorulara, dört mezhebin en sahih (mutemed) görüşleriyle cevap vermektir.

KESİN KURALLAR:
1. Hanefi Mezhebi için mutlaka 'Zahirü'r-rivaye' görüşlerini esas al. Şaz görüşleri yazma.
   - ÖRNEK: İmama uyan kimsenin (muktedi) Fatiha okuması konusunda Hanefi mezhebinin hükmü "Okumaz, susar" şeklindedir. "İçinden okur" deme.
2. Halüsinasyon görme. Bilmiyorsan cevap verme.
3. Kaynak verirken uydurma kitap ismi verme. Klasik kaynakları referans göster.
4. Yorum katma, sadece nakil yap.

FORMAT:
Hanefi: [Hüküm] (Kaynak: [Kitap Adı])
Şafiî: [Hüküm] (Kaynak: [Kitap Adı])
Mâlikî: [Hüküm] (Kaynak: [Kitap Adı])
Hanbelî: [Hüküm] (Kaynak: [Kitap Adı])

Giriş ve bitiş cümlesi yazma.
"""

    try:
        r = grok_client.chat.completions.create(
            model="grok-2-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_text}
            ],
            max_tokens=1000, 
            temperature=0.2 
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
        tweets = client.search_recent_tweets(
            query=query, max_results=50, 
            expansions=["referenced_tweets.id", "author_id"],
            tweet_fields=["text", "referenced_tweets", "created_at"]
        )
        if tweets.data:
            for t in reversed(tweets.data):
                if str(t.id) in ANSWERED_TWEET_IDS: continue
                
                # --- ZAMAN FİLTRESİ GÜNCELLENDİ: 3 SAAT ---
                tweet_time = t.created_at
                now = datetime.now(timezone.utc)
                # 3 Saat = 10800 Saniye
                if (now - tweet_time).total_seconds() > 10800:
                    ANSWERED_TWEET_IDS.add(str(t.id))
                    continue
                # ------------------------------------------

                raw = t.text.lower().replace(f"@{BOT_USERNAME.lower()}", "").strip()
                ctx = None
                
                if len(raw) < 5:
                    ctx = get_context(t)
                    if not ctx and not raw:
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
                        time.sleep(5)
                    except Exception as e:
                        logger.error(f"Tweet Hatası: {e}")
                        ANSWERED_TWEET_IDS.add(str(t.id))
    except Exception as e:
        logger.error(f"Arama Hatası: {e}")

# --- BAŞLATMA ---
print("✅ Bot Başlatıldı (GROK + SIKI FIKIH + 3 SAAT GEÇMİŞ)")
BOT_USERNAME = get_bot_username()

try:
    logger.info("📂 Geçmiş taranıyor...")
    my_tweets = client.get_users_tweets(id=BOT_ID, max_results=50, tweet_fields=["referenced_tweets"])
    if my_tweets.data:
        for t in my_tweets.data:
            if t.referenced_tweets and t.referenced_tweets[0].type == 'replied_to':
                ANSWERED_TWEET_IDS.add(str(t.referenced_tweets[0].id))
except: pass

while True:
    tweet_loop()
    time.sleep(90)

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

# --- CLIENT BAŞLATMA ---
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

    # --- SIKI FIKIH, DELİL VE REFERANS ANAYASASI ---
    system_prompt = """
    Sen Ehl-i Sünnet vel-Cemaat çizgisinde, dört mezhebin fıkıh usulüne ve furuuna hakim bir fıkıh uzmanısın.

    GÖREVİN:
    Kullanıcının sorusuna; önce meselenin genel hükmünü özetleyerek, ardından dört mezhebin delilli ve kaynaklı görüşleriyle cevap vermektir.

    KESİN KURALLAR:
    1. GİRİŞ KISMI: "Meselenin Özü:" başlığı ile konuyu 1 cümleyle özetle.
    
    2. DELİL HASSASİYETİ (AYET/HADİS):
       - Hükmü yazarken dayandığı Ayet veya Hadisi mutlaka belirt.
       - AYET İSE: Mutlaka Sure Adı ve Ayet Numarasını yaz. (Örn: "...Nisa Suresi 43. ayet gereği...")
       - HADİS İSE: Kütüb-i Sitte'deki yerini belirt. (Örn: "...hadis-i şerifine (Buhari, Savm, 3) dayanarak...")

    3. KAYNAK VE NUMARA HASSASİYETİ (ÇOK ÖNEMLİ):
       - Kitap ismi verirken sadece eser adını değil, mümkünse CİLT/SAYFA veya HADİS NUMARASINI da belirt.
       - Format: "Yazar - Eser, [Cilt/Sayfa]" veya "Hadis Kaynağı, [Bölüm], [No]"
       - Örn: "İbn Abidin - Reddü'l-Muhtar, Cilt 2, s.450"
       - Örn: "İmam Nevevi - El-Mecmu, 4/120"
       - Örn: "Buhari, İman, 4"
       - Asla sadece "Mecmu" veya "Muğni" deme, tam referans ver.

    4. HANEFİ UYARISI: Hanefi mezhebinde mutlaka 'Zahirü'r-rivaye' görüşünü esas al.

    ÇIKTI FORMATI:
    Meselenin Özü: [Özet]

    Hanefi: [Hüküm + Ayet/Hadis Delili] (Kaynak: [Yazar - Eser, Cilt/Sayfa])
    Şafiî: [Hüküm + Ayet/Hadis Delili] (Kaynak: [Yazar - Eser, Cilt/Sayfa])
    Mâlikî: [Hüküm + Ayet/Hadis Delili] (Kaynak: [Yazar - Eser, Cilt/Sayfa])
    Hanbelî: [Hüküm + Ayet/Hadis Delili] (Kaynak: [Yazar - Eser, Cilt/Sayfa])

    Başka hiçbir giriş veya bitiş cümlesi yazma.
    """

    try:
        r = grok_client.chat.completions.create(
            model="grok-3", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_text}
            ],
            max_tokens=1200, 
            temperature=0.2 # Ciddiyet (Halüsinasyon engelleme)
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
                
                # ZAMAN FİLTRESİ: 3 SAAT
                tweet_time = t.created_at
                now = datetime.now(timezone.utc)
                if (now - tweet_time).total_seconds() > 10800:
                    ANSWERED_TWEET_IDS.add(str(t.id))
                    continue

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
                        logger.error(f"Tweet Gönderme Hatası: {e}")
                        ANSWERED_TWEET_IDS.add(str(t.id))
    except Exception as e:
        logger.error(f"Arama Hatası: {e}")

# --- BAŞLATMA ---
print("✅ Bot Başlatıldı (GROK-3 + CİLT/SAYFA REFERANSLI)")
BOT_USERNAME = get_bot_username()

# Geçmiş tweetleri hafızaya al
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
    time.sleep(90)

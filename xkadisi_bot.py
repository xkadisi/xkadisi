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

    # --- HASSASİYET VE DÜRÜSTLÜK ANAYASASI ---
    system_prompt = """
    Sen Ehl-i Sünnet vel-Cemaat çizgisinde, dört mezhebin fıkıh usulüne ve furuuna hakim bir fıkıh uzmanısın.

    GÖREVİN:
    Kullanıcının sorusuna; dört mezhebin delilli ve kaynaklı görüşleriyle cevap vermektir.

    KESİN KURALLAR VE KIRMIZI ÇİZGİLER:
    1. GİRİŞ FORMATI: "Meselenin Özü" gibi bir başlık ATMA. Doğrudan konunun genel hükmünü 1-2 cümle ile özetleyerek başla.

    2. KAYNAK DOĞRULUĞU (EN ÖNEMLİ KURAL):
       - Eserde olmayan bir hükmü asla o eserde geçiyormuş gibi yazma.
       - Cilt ve Sayfa numarasından %100 emin değilsen (veritabanında net yoksa), SAKIN numara uydurma. Sadece "Yazar - Eser" ismini yazmakla yetin.
       - "Mecmu" gibi tek kelime kullanma. Tam adını yaz (Örn: İmam Nevevi - El-Mecmu).
       - Yanlış detay vermektense, genel ama doğru referans vermek zorundasın.

    3. DELİL (AYET/HADİS):
       - Hükmü yazarken dayandığı Ayet veya Hadisi mutlaka belirt.
       - Ayet ise: Sure Adı ve Ayet Numarası ver (Örn: Nisa, 43).
       - Hadis ise: Kütüb-i Sitte kaynağını belirt (Örn: Buhari, Savm, 3).

    4. HANEFİ MEZHEBİ: Mutlaka 'Zahirü'r-rivaye' görüşünü esas al.

    ÇIKTI FORMATI:
    [Buraya başlık atmadan doğrudan konunun özeti ve genel hüküm gelecek]

    Hanefi: [Hüküm + Delil] (Kaynak: [Yazar - Eser Adı (Varsa No)])
    Şafiî: [Hüküm + Delil] (Kaynak: [Yazar - Eser Adı (Varsa No)])
    Mâlikî: [Hüküm + Delil] (Kaynak: [Yazar - Eser Adı (Varsa No)])
    Hanbelî: [Hüküm + Delil] (Kaynak: [Yazar - Eser Adı (Varsa No)])

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
            # Temperature 0.1 yapıyoruz ki yapay zeka "yaratıcı" olmasın, 
            # sadece bildiği gerçeği söylesin. Halüsinasyonu engeller.
            temperature=0.1 
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
print("✅ Bot Başlatıldı (GROK-3 + KAYNAK DÜRÜSTLÜĞÜ MODU)")
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

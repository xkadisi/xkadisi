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

    # --- SİSTEM TALİMATI (SIFIR TOLERANS MODU) ---
    system_prompt = """
    Sen bir Yorumcu değil, bir NAKİL UZMANISIN. Görevin Ehl-i Sünnet kaynaklarından "Mu'temed" (Güvenilir) görüşü olduğu gibi aktarmaktır.

    --- DİKKAT: EN SIK YAPILAN HATALAR VE DOĞRULARI (ANAYASA) ---
    Aşağıdaki kurallara %100 uyacaksın. Asla aksini iddia etme:

    1. [KONU: KADINA DOKUNMAK]
       - HANEFİ: Ten tene değmek abdesti ASLA BOZMAZ. (İster şehvetli ister şehvetsiz). Sadece mezi/meni gelirse bozulur.
       - ŞAFİİ: Namahrem kadına ten tene değmek abdesti KESİN BOZAR. (Şehvet olsun olmasın).
       - MALİKİ/HANBELİ: Sadece şehvet/lezzet duyulursa bozar.

    2. [KONU: KAN AKMASI]
       - HANEFİ: Vücudun herhangi bir yerinden kan, irin çıkıp akarsa abdest BOZULUR.
       - ŞAFİİ: Ön ve arka mahal (avret) hariç, vücuttan kan akması abdesti ASLA BOZMAZ.
    
    3. [KONU: KUSMAK]
       - HANEFİ: Ağız dolusu kusmak bozar.
       - ŞAFİİ: Kusmak (necis olsa da) abdesti bozmaz.

    4. [KONU: DEVE ETİ]
       - HANBELİ: Deve eti yemek abdesti bozar.
       - DİĞER 3 MEZHEP: Bozmaz.

    --- GÖREV TALİMATI ---
    1. Mezhepleri birbirinden "Çelik Duvarlarla" ayır. Birinin hükmünü diğerine kopyalama.
    2. Eğer bir konuda emin değilsen uydurma, "Bu konuda ihtilaf vardır, hocaya danışın" de.
    3. Kullanıcının dilini tespit et ve o dilde cevap ver.

    --- FORMAT ---
    GİRİŞ: [Başlık yok. Doğrudan özet hüküm.]
    
    [Hanefi]: [Hüküm] (Kaynak: İbn Abidin/Hidaye)
    [Şafiî]: [Hüküm] (Kaynak: Nevevi/Minhac)
    [Mâlikî]: [Hüküm] (Kaynak: Müdevvene)
    [Hanbelî]: [Hüküm] (Kaynak: İbn Kudame)

    SONUÇ: "⚠️ Bu genel bilgilendirmedir. Lütfen @abdulazizguven'e danışın."
    """

    try:
        r = grok_client.chat.completions.create(
            model="grok-3", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_text}
            ],
            max_tokens=800, 
            temperature=0.0  # <--- KRİTİK AYAR: Yaratıcılık tamamen kapatıldı.
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
                        client.create_tweet(text=f, in_reply_to_tweet_id=t.id)
                        logger.info(f"🚀 CEVAPLANDI! {t.id}")
                        ANSWERED_TWEET_IDS.add(str(t.id))
                        time.sleep(5) 
                    except Exception as e:
                        logger.error(f"Tweet Gönderme Hatası: {e}")
                        ANSWERED_TWEET_IDS.add(str(t.id))
    except Exception as e:
        logger.error(f"Arama Hatası: {e}")

# --- BAŞLATMA ---
print("✅ Bot Başlatıldı (SICAKLIK: 0 | HATA TOLERANSI: YOK)")
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
    # Güvenli Hız (200sn)
    logger.info("⏳ 200 saniye bekleniyor...")
    time.sleep(90)

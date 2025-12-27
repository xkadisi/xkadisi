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
ANSWERED_DM_IDS = set() 
BOT_USERNAME = None

def get_bot_username():
    global BOT_USERNAME
    global BOT_ID
    try:
        me = client.get_me()
        if me.data:
            BOT_USERNAME = me.data.username
            BOT_ID = me.data.id 
            logger.info(f"✅ Bot Kimliği: @{BOT_USERNAME} (ID: {BOT_ID})")
            return BOT_USERNAME
    except Exception:
        return "XKadisi"

# --- GELİŞMİŞ FETVA FONKSİYONU ---
def get_fetva(soru, context=None):
    prompt_text = f"Soru: {soru}"
    if context: prompt_text += f"\n(Bağlam: '{context}')"

    system_prompt = """
    Sen Ehl-i Sünnet vel-Cemaat çizgisinde, dört mezhebin fıkıh usulüne ve furuuna hakim bir fıkıh uzmanısın.

    GÖREVİN:
    Kullanıcının sorusuna dört mezhebin delilli ve kaynaklı görüşleriyle cevap vermektir.

    --- EVRENSEL DİL KURALI ---
    1. Kullanıcının sorusunun dilini OTOMATİK TESPİT ET.
    2. Cevabı (Özet, Hükümler, Açıklamalar ve SON UYARI) TAMAMEN o dilde ver.
    3. Mezhep isimlerini o dile çevir.
    
    KURALLAR:
    1. GİRİŞ: Başlık atma. Doğrudan konunun genel hükmünü o dilde 1-2 cümle ile özetle.
    2. KAYNAK: Kitap isimlerinde Cilt/Sayfa numarasından %100 emin değilsen uydurma, sadece "Yazar - Eser" yaz.
    3. DELİL: Ayet ise (Sure Adı, No), Hadis ise (Kütüb-i Sitte Kaynağı) belirt.
    4. HANEFİ: Mutlaka 'Zahirü'r-rivaye' görüşünü esas al.

    --- ZORUNLU SONUÇ CÜMLESİ (FOOTER) ---
    Cevabın en sonuna, kullandığın dilde tam olarak şu manaya gelen uyarıyı çevirerek ekle:
    "⚠️ Bu genel bilgilendirmedir. Lütfen @abdulazizguven'e danışın."

    ÇIKTI FORMATI:
    [Buraya doğrudan özet cümlesi gelecek, başlık yok]

    [Mezhep Adı 1]: [Hüküm] (Kaynak/Source: [Eser])
    [Mezhep Adı 2]: [Hüküm] (Kaynak/Source: [Eser])
    [Mezhep Adı 3]: [Hüküm] (Kaynak/Source: [Eser])
    [Mezhep Adı 4]: [Hüküm] (Kaynak/Source: [Eser])

    [Çevrilmiş Zorunlu Uyarı Mesajı]
    """

    try:
        r = grok_client.chat.completions.create(
            model="grok-3", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_text}
            ],
            max_tokens=1000, 
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

# --- DM KONTROL FONKSİYONU ---
def check_dms():
    global ANSWERED_DM_IDS
    try:
        # DÜZELTİLEN SATIR: expansion -> expansions (çoğul olmalı)
        response = client.get_direct_message_events(max_results=10, expansions=['sender_id'])
        
        if not response.data: return

        for event in response.data:
            if event.event_type == 'MessageCreate':
                dm_id = event.id
                # DM verisi bazen karmaşık olabilir, güvenli erişim
                if event.message_create and 'sender_id' in event.message_create:
                    sender_id = event.message_create['sender_id']
                else:
                    continue
                
                # Mesajı atan ben değilsem VE daha önce cevaplamadıysam
                if str(sender_id) != str(BOT_ID) and dm_id not in ANSWERED_DM_IDS:
                    
                    msg = "Merhaba! 👋\n\nDM üzerinden soru alımımız henüz aktif değildir (Yakında açılacaktır).\n\nLütfen sorunuzu beni (@XKadisi) etiketleyerek TWEET olarak atınız. Anında cevaplayacağım.\n\nAnlayışınız için teşekkürler!"
                    
                    try:
                        client.create_direct_message(participant_id=sender_id, text=msg)
                        logger.info(f"📩 DM OTO-CEVAP yollandı: {sender_id}")
                        ANSWERED_DM_IDS.add(dm_id)
                        time.sleep(2)
                    except Exception as e:
                        logger.error(f"DM Gönderme Hatası: {e}")
                        ANSWERED_DM_IDS.add(dm_id) 

    except Exception as e:
        # 403 alırsanız Developer Portal'dan 'Read, Write, and Direct Messages' iznini kontrol edin.
        logger.error(f"DM Kontrol Hatası: {e}")

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
print("✅ Bot Başlatıldı (TWEET + DM OTO CEVAP [FIXED])")
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
    check_dms()
    time.sleep(90)

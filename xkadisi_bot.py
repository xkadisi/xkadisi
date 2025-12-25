# -*- coding: utf-8 -*-
import tweepy
from openai import OpenAI
import time
import os
import logging
import sys
from datetime import datetime, timedelta, timezone

# --- LOGLAMA ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- KEYLER ---
required_keys = ["BEARER_TOKEN", "CONSUMER_KEY", "CONSUMER_SECRET", "ACCESS_TOKEN", "ACCESS_TOKEN_SECRET", "GROK_API_KEY"]
if not all(os.environ.get(k) for k in required_keys):
    logger.error("❌ HATA: Keyler eksik!")
    time.sleep(10)
    exit(1)

# --- AYARLAR ---
BOT_ID = 1997244309243060224  

# Client
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

# --- HAFIZA ---
ANSWERED_TWEET_IDS = set()
ANSWERED_DM_IDS = set() 
USER_QUESTION_COUNTS = {} 
KNOWN_FOLLOWERS = set()
KNOWN_NON_FOLLOWERS = set()
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

def is_user_following_safe(user_id):
    user_str = str(user_id)
    if user_str in KNOWN_FOLLOWERS: return True
    if user_str in KNOWN_NON_FOLLOWERS: return False
        
    try:
        user = client.get_user(id=user_id, user_fields=["connection_status"])
        if user.data and user.data.connection_status:
            if 'following' in user.data.connection_status:
                KNOWN_FOLLOWERS.add(user_str)
                if user_str in KNOWN_NON_FOLLOWERS: KNOWN_NON_FOLLOWERS.remove(user_str)
                return True
            else:
                KNOWN_NON_FOLLOWERS.add(user_str)
                return False
        return False
    except Exception:
        return False

# --- DM KONTROL ---
def check_dms():
    global ANSWERED_DM_IDS, USER_QUESTION_COUNTS
    logger.info("📨 DM Kutusu taranıyor...")
    
    try:
        events = client.get_direct_message_events(max_results=10, event_types=["MessageCreate"])
        if not events.data: return

        for event in reversed(events.data):
            if str(event.id) in ANSWERED_DM_IDS: continue

            created_timestamp = int(event.created_at) / 1000 
            msg_time = datetime.fromtimestamp(created_timestamp, timezone.utc)
            now = datetime.now(timezone.utc)
            if (now - msg_time).total_seconds() > 7200:
                ANSWERED_DM_IDS.add(str(event.id))
                continue

            sender_id = event.message_create['sender_id']
            text = event.message_create['message_data']['text']

            if str(sender_id) == str(BOT_ID): continue

            sender_str = str(sender_id)
            soru_sayisi = USER_QUESTION_COUNTS.get(sender_str, 0)
            
            if soru_sayisi >= 1:
                if not is_user_following_safe(sender_id):
                    ANSWERED_DM_IDS.add(str(event.id))
                    continue
            
            logger.info(f"📩 İŞLENİYOR (DM): {text[:30]}...")

            fetva = get_fetva(text)
            if fetva:
                try:
                    ek_not = ""
                    if soru_sayisi == 0:
                        ek_not = "\n\n🎁 Bu sizin ilk ücretsiz sorunuzdu. Devamı için lütfen takip ediniz."
                    cevap = f"Merhaba!\n\n{fetva}\n\n⚠️ Genel bilgilendirmedir.{ek_not}"
                    client.create_direct_message(participant_id=sender_id, text=cevap)
                    logger.info(f"🚀 DM GÖNDERİLDİ! (Kime: {sender_id})")
                    ANSWERED_DM_IDS.add(str(event.id))
                    USER_QUESTION_COUNTS[sender_str] = soru_sayisi + 1
                    time.sleep(5)
                except Exception as e:
                    logger.error(f"DM Hata: {e}")
                    ANSWERED_DM_IDS.add(str(event.id))

    except Exception as e:
        if "Connection" in str(e) or "reset by peer" in str(e):
             logger.warning("⚠️ DM Sunucusu meşgul. Pas geçildi.")
        else:
             logger.error(f"DM Genel Hata: {e}")

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
                if (now - tweet_time).total_seconds() > 3600:
                    ANSWERED_TWEET_IDS.add(str(t.id))
                    continue

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
print("✅ Bot Başlatıldı (SOĞUK BAŞLANGIÇ MODU)")
BOT_USERNAME = get_bot_username()

try:
    my_tweets = client.get_users_tweets(id=BOT_ID, max_results=50, tweet_fields=["referenced_tweets"])
    if my_tweets.data:
        for t in my_tweets.data:
            if t.referenced_tweets and t.referenced_tweets[0].type == 'replied_to':
                ANSWERED_TWEET_IDS.add(str(t.referenced_tweets[0].id))
except: pass

# --- KRİTİK DEĞİŞİKLİK BURADA ---
# Başlangıcı 1 yapıyoruz ki ilk açılışta DM'e bakmasın.
loop_counter = 1 

while True:
    # 1. Tweetleri her zaman kontrol et (Limitleri daha esnek)
    tweet_loop()
    
    # 2. DM'leri sadece 4 turda bir kontrol et (10-12 dakikada bir)
    # modül (%) işlemi kalana bakar. 
    # 1. Tur: 1/4 kalan 1 -> BAKMA
    # 2. Tur: 2/4 kalan 2 -> BAKMA
    # 3. Tur: 3/4 kalan 3 -> BAKMA
    # 4. Tur: 4/4 kalan 0 -> BAK!
    if loop_counter % 4 == 0:
        try:
            check_dms()
        except Exception as e:
            logger.error(f"Döngü hatası: {e}")
    else:
        logger.info(f"⏳ DM kontrolü için sıranın gelmesi bekleniyor... ({loop_counter % 4}/4)")

    loop_counter += 1
    
    # Bekleme (150 saniye)
    time.sleep(150)

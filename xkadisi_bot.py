# -*- coding: utf-8 -*-
import tweepy
from openai import OpenAI
import time
import os
import logging
import sys

# --- LOGLAMA ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- AYARLAR ---
# ID'yi yine de tutuyoruz ama asıl işimiz Kullanıcı Adı (Username) ile olacak.
BOT_ID = 1997244309243060224  

# Environment Variables
if not os.environ.get("BEARER_TOKEN"):
    logger.error("❌ HATA: Keyler eksik!")
    time.sleep(10)
    exit(1)

# Client Başlatma
client = tweepy.Client(
    bearer_token=os.environ.get("BEARER_TOKEN"),
    consumer_key=os.environ.get("CONSUMER_KEY"),
    consumer_secret=os.environ.get("CONSUMER_SECRET"),
    access_token=os.environ.get("ACCESS_TOKEN"),
    access_token_secret=os.environ.get("ACCESS_TOKEN_SECRET"),
    wait_on_rate_limit=True  # 429 Limitinde otomatik bekle
)

grok_client = OpenAI(
    api_key=os.environ.get("GROK_API_KEY"),
    base_url="https://api.x.ai/v1"
)

# Global Değişkenler
ANSWERED_IDS = set()
BOT_USERNAME = None  # Otomatik doldurulacak (örn: XKadisi)

def get_bot_username():
    """Botun kullanıcı adını (handle) öğrenir. Arama sorgusu için şarttır."""
    global BOT_USERNAME
    try:
        me = client.get_me()
        if me.data:
            BOT_USERNAME = me.data.username
            logger.info(f"✅ Bot Kullanıcı Adı Tespit Edildi: @{BOT_USERNAME}")
            return BOT_USERNAME
    except Exception as e:
        logger.error(f"Kullanıcı adı çekilemedi: {e}")
        # Eğer API hatası olursa manuel fallback
        return "XKadisi"

def get_context(tweet):
    """Tweet bir yanıtsa veya alıntıysa üst tweeti çeker."""
    if not tweet.referenced_tweets:
        return None
    
    for ref in tweet.referenced_tweets:
        if ref.type in ['replied_to', 'quoted']:
            try:
                parent = client.get_tweet(ref.id, tweet_fields=["text"])
                if parent.data: return parent.data.text
            except: pass
    return None

def get_fetva(soru, context=None):
    """Grok-3 Fetva"""
    prompt_text = f"Kullanıcı sorusu: {soru}"
    if context: prompt_text += f"\n(Bağlam/Konu: '{context}')"

    prompt = f"""
{prompt_text}

Dört Büyük Sünni Mezhebe (Hanefi, Şafiî, Mâlikî, Hanbelî) göre bu konunun detaylı ve delilli hükmünü açıkla.
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

def load_history():
    """Hafıza Tazeleme (Başlangıçta)"""
    ids = set()
    logger.info("📂 Hafıza yükleniyor...")
    try:
        # Son 100 cevabımıza bakıyoruz
        my_tweets = client.get_users_tweets(id=BOT_ID, max_results=100, tweet_fields=["referenced_tweets"])
        if my_tweets.data:
            for t in my_tweets.data:
                if t.referenced_tweets:
                    for r in t.referenced_tweets:
                        if r.type == 'replied_to': ids.add(str(r.id))
    except Exception: pass
    return ids

def main_loop():
    global ANSWERED_IDS
    
    # SORGUMUZ: "@XKadisi" geçen tweetler (Retweetler hariç, kendi tweetlerimiz hariç)
    query = f"@{BOT_USERNAME} -is:retweet -from:{BOT_USERNAME}"
    
    logger.info(f"🔎 ARAMA YAPILIYOR: '{query}'")
    
    try:
        # get_users_mentions YERİNE search_recent_tweets kullanıyoruz!
        # Bu yöntem bildirim kutusuna değil, tüm Twitter'a bakar.
        tweets = client.search_recent_tweets(
            query=query,
            max_results=20, # Her seferinde en yeni 20 sonuç
            expansions=["referenced_tweets.id", "author_id"],
            tweet_fields=["created_at", "text", "author_id", "referenced_tweets"]
        )
    except Exception as e:
        logger.error(f"Arama Hatası: {e}")
        time.sleep(60)
        return

    if not tweets.data:
        logger.info("📭 Arama sonucu boş.")
        return

    logger.info(f"📥 {len(tweets.data)} tweet bulundu.")

    for tweet in reversed(tweets.data):
        # Hafıza kontrolü
        if str(tweet.id) in ANSWERED_IDS:
            continue
            
        logger.info(f"👁️ İŞLENİYOR: {tweet.text[:40]}... (ID: {tweet.id})")
        
        # İşlem Mantığı (Aynı)
        raw_text = tweet.text.lower().replace(f"@{BOT_USERNAME.lower()}", "").strip()
        context = None
        
        if len(raw_text) < 5:
            context = get_context(tweet)
            if not context and not raw_text:
                ANSWERED_IDS.add(str(tweet.id)) # Boşsa hafızaya at geç
                continue
        
        q = raw_text if raw_text else "Bu durumun hükmü nedir?"
        fetva = get_fetva(q, context)
        
        if fetva:
            try:
                msg = f"Merhaba!\n\n{fetva}\n\n⚠️ Bu genel bilgilendirmedir, mutlak fetva değildir. Lütfen @abdulazizguven'e danışın."
                client.create_tweet(text=msg, in_reply_to_tweet_id=tweet.id)
                logger.info(f"🚀 CEVAPLANDI! {tweet.id}")
                ANSWERED_IDS.add(str(tweet.id))
                time.sleep(5)
            except Exception as e:
                logger.error(f"Tweet hatası: {e}")
                ANSWERED_IDS.add(str(tweet.id)) # Hata alsa da hafızaya al

# --- BAŞLATMA ---
print("✅ Bot Başlatıldı (SEARCH API / ARAMA MODU)")
BOT_USERNAME = get_bot_username() # Kullanıcı adını öğren
ANSWERED_IDS = load_history() # Geçmişi öğren

while True:
    main_loop()
    # Search API limiti (Basic): 60 istek / 15 dk
    # 60 saniyede 1 istek = 15 istek / 15 dk (Gayet güvenli)
    time.sleep(60)

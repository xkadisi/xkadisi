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
BOT_ID = 1997244309243060224  

# Keyler
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

# Clientlar
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

# Global Değişkenler
LAST_SEEN_ID = None 

# --- YENİ FONKSİYON: ÜST TWEETİ GETİR ---
def get_parent_tweet_text(mention):
    """Eğer mention bir yanıtsa, cevap verilen (üstteki) tweetin metnini çeker."""
    if not mention.referenced_tweets:
        return None
    
    for ref in mention.referenced_tweets:
        if ref.type == 'replied_to':
            try:
                # Üst tweetin metnini çekiyoruz
                parent_tweet = client.get_tweet(
                    ref.id, 
                    tweet_fields=["text", "author_id"]
                )
                if parent_tweet.data:
                    return parent_tweet.data.text
            except Exception as e:
                logger.error(f"Üst tweet çekilemedi: {e}")
                return None
    return None

def get_fetva(soru, is_context=False):
    """Grok-3 Fetva Üretici"""
    
    # Eğer soru üst tweetten geldiyse promptu ona göre ayarlayalım
    if is_context:
        prompt_intro = f"Kullanıcı beni şu ifadenin altına etiketledi, lütfen bu duruma/söze dair fıkhi hükmü ver: '{soru}'"
    else:
        prompt_intro = f"Kullanıcı sorusu: {soru}"

    prompt = f"""
{prompt_intro}

Dört büyük Sünni mezhebine göre bu konunun hükmünü detaylı ve anlaşılır bir şekilde açıkla.
Cevapların kısa olmasın, konuyu doyurucu bir şekilde izah et.
Her mezhep için hükmü belirttikten sonra, parantez içinde mutlaka dayandığı delili veya fıkıh kitabını yaz.

Format:
Hanefi: [Hüküm] (Kaynak: el-Hidâye)
Şafiî: [Hüküm] (Kaynak: el-Mecmû')
Mâlikî: [Hüküm] (Kaynak: Muvatta)
Hanbelî: [Hüküm] (Kaynak: el-Muğnî)

Giriş/Bitiş cümlesi yazma.
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
    replied_ids = set()
    try:
        my_tweets = client.get_users_tweets(id=BOT_ID, max_results=50, tweet_fields=["referenced_tweets"])
        if my_tweets.data:
            for tweet in my_tweets.data:
                if tweet.referenced_tweets:
                    for ref in tweet.referenced_tweets:
                        if ref.type == 'replied_to':
                            replied_ids.add(str(ref.id))
    except Exception:
        pass
    return replied_ids

def process_mention(mention):
    # 1. Metni temizle
    text_content = mention.text.lower().replace("@xkadisi", "").strip()
    
    final_soru = ""
    is_context_search = False

    # 2. Eğer metin BOŞ ise veya çok kısaysa (sadece etiket atılmışsa)
    if not text_content or len(text_content) < 3:
        logger.info(f"🤔 Soru boş, üst tweet (Bağlam) kontrol ediliyor... ID: {mention.id}")
        parent_text = get_parent_tweet_text(mention)
        
        if parent_text:
            logger.info(f"💡 BAĞLAM BULUNDU: {parent_text[:50]}...")
            final_soru = parent_text
            is_context_search = True
        else:
            logger.info("❌ Üst tweet bulunamadı veya okunamadı. Pas geçiliyor.")
            return
    else:
        # Kullanıcı bizzat soru sormuş
        final_soru = text_content

    # 3. Fetvayı al
    logger.info(f"📩 İŞLENİYOR: {final_soru[:30]}...")
    fetva_metni = get_fetva(final_soru, is_context=is_context_search)
    
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
        time.sleep(10) 
    except Exception as e:
        logger.error(f"Tweet atma hatası: {e}")

def main_loop():
    global LAST_SEEN_ID
    answered_ids = get_replied_ids()
    
    logger.info(f"🔄 Tarama (Ref: {LAST_SEEN_ID})...")
    
    try:
        # referenced_tweets alanını ekledik ki yanıt olup olmadığını anlayalım
        mentions = client.get_users_mentions(
            id=BOT_ID,
            since_id=LAST_SEEN_ID,
            max_results=10, 
            tweet_fields=["created_at", "text", "author_id", "referenced_tweets"] 
        )
    except Exception as e:
        logger.error(f"API Hatası: {e}")
        time.sleep(60)
        return

    if not mentions.data:
        return

    logger.info(f"🔔 {len(mentions.data)} yeni bildirim.")
    
    for mention in reversed(mentions.data):
        LAST_SEEN_ID = mention.id
        
        if str(mention.author_id) == str(BOT_ID): continue
        if str(mention.id) in answered_ids: continue
        
        process_mention(mention)
        answered_ids.add(str(mention.id))

# --- ÇALIŞTIR ---
print("✅ Bot Başlatıldı (Context/Bağlam Modu)")
print("Artık boş etiketlemelerde üst tweeti okuyacak.")

while True:
    main_loop()
    time.sleep(60)

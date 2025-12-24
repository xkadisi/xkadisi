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

# Key Kontrolü
if not os.environ.get("BEARER_TOKEN"):
    print("❌ Keyler eksik! Lütfen Environment Variables kontrol edin.")
    time.sleep(10)
    exit(1)

# Rate Limit Koruması Aktif
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

LAST_SEEN_ID = None 
ANSWERED_IDS = set() # Hafızayı global yapıyoruz

def get_parent_tweet_text(mention):
    """Reply veya Quote içeriğini bulur."""
    if not mention.referenced_tweets:
        return None
    
    for ref in mention.referenced_tweets:
        if ref.type in ['replied_to', 'quoted']:
            try:
                parent_tweet = client.get_tweet(
                    ref.id, 
                    tweet_fields=["text", "author_id"]
                )
                if parent_tweet.data:
                    return parent_tweet.data.text
            except Exception:
                pass     
    return None

def get_fetva(soru, is_context=False):
    if is_context:
        prompt_intro = f"Kullanıcı beni şu ifadenin altına etiketledi (veya alıntıladı). Buna dair fıkhi hükmü ver: '{soru}'"
    else:
        prompt_intro = f"Kullanıcı sorusu: {soru}"

    prompt = f"""
{prompt_intro}

Dört büyük Sünni mezhebine göre bu konunun hükmünü detaylı, delilli ve anlaşılır bir şekilde açıkla.

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

def get_replied_ids_once():
    """Sadece başlangıçta çalışır: Geçmiş cevapları hafızaya alır."""
    ids = set()
    try:
        logger.info("📂 Geçmiş tweetler taranıyor (Başlangıç İşlemi)...")
        my_tweets = client.get_users_tweets(id=BOT_ID, max_results=50, tweet_fields=["referenced_tweets"])
        if my_tweets.data:
            for tweet in my_tweets.data:
                if tweet.referenced_tweets:
                    for ref in tweet.referenced_tweets:
                        if ref.type == 'replied_to':
                            ids.add(str(ref.id))
    except Exception as e:
        logger.error(f"Geçmiş tarama hatası: {e}")
    return ids

def process_mention(mention):
    text_content = mention.text.lower().replace("@xkadisi", "").strip()
    final_soru = ""
    is_context_search = False

    if not text_content or len(text_content) < 3:
        logger.info(f"🤔 Soru boş, bağlam aranıyor... ID: {mention.id}")
        parent_text = get_parent_tweet_text(mention)
        if parent_text:
            final_soru = parent_text
            is_context_search = True
        else:
            return
    else:
        final_soru = text_content

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
        time.sleep(5) 
        return True # Başarılı olduğunu bildir
    except Exception as e:
        logger.error(f"Tweet atma hatası: {e}")
        return False

def main_loop():
    global LAST_SEEN_ID
    # ANSWERED_IDS artık global, her döngüde yeniden çekmiyoruz.
    
    logger.info(f"🔄 Tarama (Ref: {LAST_SEEN_ID})...")
    
    try:
        mentions = client.get_users_mentions(
            id=BOT_ID,
            since_id=LAST_SEEN_ID,
            max_results=10, 
            tweet_fields=["created_at", "text", "author_id", "referenced_tweets"] 
        )
    except Exception as e:
        logger.error(f"Beklenmedik Hata: {e}")
        # Hata alınca biraz uzun bekle
        time.sleep(120)
        return

    if not mentions.data:
        return

    logger.info(f"🔔 {len(mentions.data)} yeni bildirim.")
    
    for mention in reversed(mentions.data):
        LAST_SEEN_ID = mention.id
        
        if str(mention.author_id) == str(BOT_ID): continue
        if str(mention.id) in ANSWERED_IDS: continue
        
        basarili = process_mention(mention)
        
        if basarili:
            # Cevap verdiysek hafızaya ekle, bir daha sorma
            ANSWERED_IDS.add(str(mention.id))

# --- ÇALIŞTIR ---
print("✅ Bot Başlatıldı (Optimizasyonlu Mod)")

# 1. Başlangıçta SADECE BİR KEZ geçmişi öğren
ANSWERED_IDS = get_replied_ids_once()
logger.info(f"🧠 Hafızaya alınan cevap sayısı: {len(ANSWERED_IDS)}")

while True:
    main_loop()
    # 60 saniye bazen sınıra takılabilir, 75 saniye daha güvenlidir.
    time.sleep(75)

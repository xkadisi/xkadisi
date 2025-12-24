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

# Environment Variables Kontrolü
if not os.environ.get("BEARER_TOKEN"):
    print("❌ HATA: API Keyler bulunamadı!")
    time.sleep(10)
    exit(1)

# Rate Limit Koruması Açık
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

# Global Hafıza Seti
ANSWERED_IDS = set()

def get_context(mention):
    """
    Tweetin bağlamını (Reply ise üst tweeti, Quote ise alıntılananı) çeker.
    """
    if not mention.referenced_tweets:
        return None
    
    for ref in mention.referenced_tweets:
        # Quote (Alıntı) veya Replied_to (Yanıt) fark etmeksizin içeriği al
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

def get_fetva(soru, context_text=None):
    """Grok-3 Fetva Üretici"""
    
    prompt_intro = f"Kullanıcı sorusu: {soru}"
    if context_text:
        prompt_intro += f"\n\n(BAĞLAM/KONU: Kullanıcı şu metni alıntılayarak veya altına yazarak sordu: '{context_text}')"

    prompt = f"""
{prompt_intro}

Lütfen Dört Büyük Sünni Mezhebine (Hanefi, Şafiî, Mâlikî, Hanbelî) göre bu konunun fıkhi hükmünü detaylı ve delilli açıkla.

Format:
Hanefi: [Hüküm] (Kaynak: el-Hidâye)
Şafiî: [Hüküm] (Kaynak: el-Mecmû')
Mâlikî: [Hüküm] (Kaynak: Muvatta)
Hanbelî: [Hüküm] (Kaynak: el-Muğnî)

Giriş ve sonuç cümlesi yazma. Sadece formatı ver.
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

def load_history():
    """Bot açıldığında 'Ben daha önce kime cevap verdim?' diye hafızayı doldurur."""
    ids = set()
    logger.info("📂 Geçmiş cevaplar taranıyor (Hafıza Tazeleme)...")
    try:
        # Botun attığı son 60 tweeti (cevapları) kontrol et
        my_tweets = client.get_users_tweets(
            id=BOT_ID, 
            max_results=60, 
            tweet_fields=["referenced_tweets"]
        )
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
    """Tek bir mention'ı işler ve cevaplar."""
    
    # 1. Metin Temizliği
    raw_text = mention.text.lower().replace("@xkadisi", "").strip()
    context_text = None
    
    # 2. Bağlam Kontrolü
    # Eğer soru çok kısaysa (örn: "bunun hükmü ne") veya boşsa, MUTLAKA üst tweeti çek.
    if len(raw_text) < 5 or not raw_text:
        logger.info(f"🔍 Bağlam aranıyor... ID: {mention.id}")
        context_text = get_context(mention)
        
        if not context_text and not raw_text:
            logger.info("❌ Ne soru var ne bağlam. Cevap verilemiyor.")
            return False # Başarısız
    
    # 3. Fetva İste
    # Soruyu belirle (Soru varsa soru, yoksa bağlam)
    final_query = raw_text if raw_text else "Bu durumun hükmü nedir?"
    
    logger.info(f"📩 İŞLENİYOR: {final_query[:30]}... (Tweet ID: {mention.id})")
    
    fetva_metni = get_fetva(final_query, context_text)
    
    if not fetva_metni:
        return False

    # 4. Cevabı Gönder
    tam_cevap = (
        f"Merhaba!\n\n"
        f"{fetva_metni}\n\n"
        f"⚠️ Bu genel bilgilendirmedir, mutlak fetva değildir. Lütfen @abdulazizguven'e danışın."
    )

    try:
        client.create_tweet(text=tam_cevap, in_reply_to_tweet_id=mention.id)
        logger.info(f"🚀 CEVAPLANDI! Tweet ID: {mention.id}")
        time.sleep(5) # Spam koruması
        return True
    except Exception as e:
        logger.error(f"Tweet atma hatası: {e}")
        return False

def main_loop():
    """
    ÖRTÜŞMELİ TARAMA DÖNGÜSÜ
    since_id kullanmıyoruz. Her seferinde son 15 mention'ı çekip,
    'Ben buna cevap vermiş miydim?' diye ANSWERED_IDS kümesine bakıyoruz.
    """
    global ANSWERED_IDS
    
    logger.info("🔄 Tarama Başlıyor (Son 15 Mention)...")
    
    try:
        # since_id YOK. Daima en güncel 15 taneyi al.
        mentions = client.get_users_mentions(
            id=BOT_ID,
            max_results=15, 
            tweet_fields=["created_at", "text", "author_id", "referenced_tweets"] 
        )
    except Exception as e:
        logger.error(f"API Hatası: {e}")
        time.sleep(60)
        return

    if not mentions.data:
        logger.info("📭 Hiç mention yok.")
        return
    
    # Tweetleri eskiden yeniye işle
    new_count = 0
    for mention in reversed(mentions.data):
        
        # 1. Kendi tweetimiz mi?
        if str(mention.author_id) == str(BOT_ID):
            continue
            
        # 2. Zaten cevapladık mı? (Hafıza Kontrolü)
        if str(mention.id) in ANSWERED_IDS:
            continue
            
        # 3. Yeni Mention Bulundu! İşle.
        logger.info(f"✨ YENİ YAKALANDI: {mention.id}")
        basari = process_mention(mention)
        
        # İşlem denendiyse (başarılı veya başarısız) hafızaya al ki
        # döngüde sürekli deneyip API'yi yormasın veya spam yapmasın.
        ANSWERED_IDS.add(str(mention.id))
        new_count += 1

    if new_count == 0:
        logger.info("💤 Yeni işlem yapılacak tweet bulunamadı.")
    else:
        logger.info(f"✅ Bu turda {new_count} yeni tweet işlendi.")

# --- BAŞLATMA ---
print("✅ Bot Başlatıldı (No-Miss / Örtüşmeli Mod)")

# 1. Başlangıçta hafızayı yükle
ANSWERED_IDS = load_history()
logger.info(f"🧠 Hafızada {len(ANSWERED_IDS)} adet cevaplanmış tweet var.")

while True:
    main_loop()
    # 90 saniye bekleme süresi (API kotası ve güvenli overlap için ideal)
    time.sleep(90)

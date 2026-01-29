# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import tweepy
from openai import OpenAI
import time
import os
import logging
import sys
from datetime import datetime, timezone

# --- 1. WEB SUNUCUSU AYARLARI ---
app = Flask(__name__)
CORS(app) 

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

# --- CLIENT BAŞLATMA ---
# (Tweepy kısmı aynı kalsın, sadece grok_client'ı değiştir)

grok_client = OpenAI(
    api_key=os.environ.get("GROK_API_KEY"),
    base_url="https://api.x.ai/v1",
    timeout=30.0,    # 30 saniye yeterli, fazlası sistemi yorar
    max_retries=5    # Hata alırsan 5 kere dene
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

# =====================================================
# BÖLÜM A: TWITTER FETVA MANTIĞI (KISA VE NET)
# =====================================================
def get_fetva_twitter(soru, context=None):
    prompt_text = f"KULLANICI SORUSU: {soru}"
    if context: prompt_text += f"\n(BAĞLAM: '{context}')"

    # GÜNCELLENMİŞ SİSTEM (EMOJİLİ & HATASIZ)
    system_prompt = """
    Sen "X Kadısı" isminde, Ehl-i Sünnet kaynaklarına (İbn Abidin, Nevevi, İbn Kudame) hakim bir Fıkıh Uzmanısın.

    GÖREVİN:
    Sorulan meseleyi fıkıh kitaplarından tara, mezheplerin detaylarını analiz et ve görsel olarak şık bir formatta sun.

    --- GÖRSEL VE FORMAT KURALLARI (ÇOK ÖNEMLİ) ---
    1. ASLA "[Giriş Cümlesi]" veya "[Özet]" gibi şablon başlıkları YAZMA. Doğrudan konuya gir.
    2. Mezhep başlıklarını mutlaka şu EMOJİLERLE ve BÜYÜK HARFLE yaz:
       🟦 HANEFİ: [Hüküm]
       🟪 ŞAFİİ: [Hüküm]
       🟩 MALİKİ: [Hüküm]
       🟧 HANBELİ: [Hüküm]
    3. Kaynakları her satırın sonuna parantez içinde ekle. (Örn: Kaynak: İbn Abidin)

    --- FIKIH METODOLOJİSİ (HATA YAPMA!) ---
    1. TERTİP (SIRALAMA) ESASTIR:
       - Özellikle "Yemin Kefareti" gibi konularda Kur'an'daki sıralamaya uy.
       - ÖNCE: Doyurmak veya Giydirmek (Bunlar asıldır).
       - SONRA: Eğer bunlara maddi güç yetmezse Oruç tutulur. (Bot olarak "İstediğini seçer" deme, oruç fakirin seçeneğidir).
    2. ŞARTLAR:
       - Hanefi'de yemin kefareti orucu "Peş peşe" şarttır.
       - Şafii'de "Peş peşe" şart değildir (Ayrı ayrı tutulabilir).

    --- ÇIKTI ŞABLONU ---
    (Konuya dair kısa, net bir giriş paragrafı...)

    🟦 HANEFİ: ... (Kaynak: ...)
    
    🟪 ŞAFİİ: ... (Kaynak: ...)
    
    🟩 MALİKİ: ... (Kaynak: ...)
    
    🟧 HANBELİ: ... (Kaynak: ...)

    ⚠️ SONUÇ: Bu genel bilgilendirmedir. Lütfen @abdulazizguven'e danışın.
    """

    try:
        r = grok_client.chat.completions.create(
            model="grok-2-1212", # <-- GÜNCELLENDİ: En stabil sürüm budur.
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_text}
            ],
            max_tokens=1200, 
            temperature=0.1 
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Grok Hatası: {e}")
        return None
# =====================================================
# BÖLÜM B: WEB SİTESİ FETVA MANTIĞI (SOHBET + FIKIH)
# =====================================================
def get_fetva_web(soru):
    # GÜNCELLENMİŞ VE LOGLAMA EKLENMİŞ VERSİYON
    system_prompt = """
    KİMLİK:
    Sen "Fukaha Meclisi"nin yapay zeka asistanısın. Ehl-i Sünnet ve'l Cemaat çizgisinde, 4 Hak Mezhebe (Hanefi, Şafii, Maliki, Hanbeli) hakim bir fıkıh alimisin.

    MOD 1: SOHBET
    - "Selamun Aleyküm" -> "Ve Aleyküm Selam ve Rahmetullah kıymetli kardeşim."
    - "Nasılsın" -> "Hamdolsun, hizmetinizdeyiz."

    MOD 2: FIKHİ SORULAR (ASIL GÖREV)
    Eğer kullanıcı dini bir soru sorarsa:
    
    "Selamun Aleyküm kıymetli kardeşim," (Alt satır)
    "Sorunuzun cevabını Ehl-i Sünnet kaynaklarımız ışığında arz edeyim:"

    <br><br><b>📌 ÖZET HÜKÜM:</b><br>
    (Net cevap)

    <br><br><b>📖 DELİLLER VE İZAH:</b><br>
    (Detaylı açıklama)

    <br><br><b>⚖️ MEZHEP GÖRÜŞLERİ:</b><br>
    <b>🟦 HANEFİ:</b> [Hüküm] (Kaynak: İbn Abidin)<br>
    <b>🟪 ŞAFİİ:</b> [Hüküm] (Kaynak: Nevevi)<br>
    <b>🟩 MALİKİ:</b> [Hüküm] (Kaynak: Müdevvene)<br>
    <b>🟧 HANBELİ:</b> [Hüküm] (Kaynak: İbn Kudame)<br>

    <br><br><b>⚠️ SONUÇ VE TAVSİYE:</b><br>
    Kıymetli kardeşim, bu bilgiler genel fıkhi kaidelere dayanmaktadır. Durumunuzun özel detayları veya şüpheli noktalar için lütfen sitemizdeki <b>"Soru Sor"</b> butonunu kullanarak fetva alınız.<br>
    Rabbim ilminizi artırsın. (Amin).
    """
    try:
        r = grok_client.chat.completions.create(
            model="grok-2-1212", # <-- GÜNCELLENDİ: En stabil sürüm budur.
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": soru}
            ],
            max_tokens=2000, 
            temperature=0.2 
        )
        return r.choices[0].message.content
    except Exception as e:
        # İŞTE BURASI HATAYI LOGLARA YAZACAK
        logger.error(f"❌ KRİTİK HATA (WEB): {str(e)}")
        return "Şu an kaynaklara erişmekte güçlük çekiyorum. (Sistem Yöneticisine Bildirildi)"
# =====================================================
# BÖLÜM C: TWITTER DÖNGÜSÜ
# =====================================================
def twitter_loop_thread():
    global ANSWERED_TWEET_IDS, BOT_USERNAME
    logger.info("🚀 Twitter Modülü (Thread) Başlatıldı...")
    BOT_USERNAME = get_bot_username()

    try:
        my_tweets = client.get_users_tweets(id=BOT_ID, max_results=50, tweet_fields=["referenced_tweets"])
        if my_tweets.data:
            for t in my_tweets.data:
                if t.referenced_tweets and t.referenced_tweets[0].type == 'replied_to':
                    ANSWERED_TWEET_IDS.add(str(t.referenced_tweets[0].id))
    except: pass

    while True:
        try:
            query = f"@{BOT_USERNAME} -is:retweet -from:{BOT_USERNAME}"
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
                        ANSWERED_TWEET_IDS.add(str(t.id)); continue

                    raw = t.text.lower().replace(f"@{BOT_USERNAME.lower()}", "").strip()
                    ctx = None
                    if len(raw) < 5:
                        ctx = get_context(t)
                        if not ctx and not raw:
                            ANSWERED_TWEET_IDS.add(str(t.id)); continue

                    logger.info(f"👁️ TWEET İŞLENİYOR: {raw[:30]}...")
                    f = get_fetva_twitter(raw if raw else "Hüküm nedir?", ctx)
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
            logger.error(f"Döngü Hatası: {e}")
        time.sleep(200)

# =====================================================
# BÖLÜM D: WEB VE BAŞLATMA
# =====================================================
@app.route('/', methods=['GET'])
def home():
    return "X Kadısı & Fukaha Botu Aktif! 🚀"

@app.route('/sor', methods=['POST'])
def sor():
    data = request.json
    soru = data.get('soru')
    if not soru: return jsonify({"cevap": "Soru yok"}), 400
    
    logger.info(f"🌍 WEB İSTEĞİ: {soru[:20]}...")
    cevap = get_fetva_web(soru)
    return jsonify({"cevap": cevap})

t = threading.Thread(target=twitter_loop_thread)
t.start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

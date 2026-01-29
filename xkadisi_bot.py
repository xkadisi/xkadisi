# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import tweepy
from openai import OpenAI  # <--- EKLENDİ: Kodun çalışması için şart
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

# --- KEY KONTROL VE CLIENT BAŞLATMA ---
if not os.environ.get("GROK_API_KEY"):
    logger.error("❌ HATA: GROK_API_KEY eksik! Render ayarlarını kontrol edin.")

# Grok Client (Eksikti, eklendi)
grok_client = OpenAI(
    api_key=os.environ.get("GROK_API_KEY"),
    base_url="https://api.x.ai/v1",
    timeout=90.0,
    max_retries=3
)

# Twitter Client
client = tweepy.Client(
    bearer_token=os.environ.get("BEARER_TOKEN"),
    consumer_key=os.environ.get("CONSUMER_KEY"),
    consumer_secret=os.environ.get("CONSUMER_SECRET"),
    access_token=os.environ.get("ACCESS_TOKEN"),
    access_token_secret=os.environ.get("ACCESS_TOKEN_SECRET"),
    wait_on_rate_limit=True
)

BOT_ID = 1997244309243060224
ANSWERED_TWEET_IDS = set()
BOT_USERNAME = "XKadisi" 

def get_bot_username():
    global BOT_USERNAME
    try:
        me = client.get_me()
        if me.data:
            BOT_USERNAME = me.data.username
            logger.info(f"✅ Bot Kimliği: @{BOT_USERNAME}")
    except: pass
    return BOT_USERNAME

# =====================================================
# BÖLÜM A: TWITTER FETVA (Grok-3)
# =====================================================
def get_fetva_twitter(soru, context=None):
    prompt_text = f"KULLANICI SORUSU: {soru}"
    if context: prompt_text += f"\n(BAĞLAM: '{context}')"

    # SENİN İSTEDİĞİN PROMPT (DEĞİŞTİRİLMEDİ)
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
            model="grok-3", 
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
# BÖLÜM B: WEB SİTESİ FETVA (Grok-3)
# =====================================================
def get_fetva_web(soru):
    # SENİN İSTEDİĞİN PROMPT (DEĞİŞTİRİLMEDİ)
    system_prompt = """
    KİMLİK:
    Sen "Fukaha Meclisi"nin yapay zeka asistanısın. Ehl-i Sünnet ve'l Cemaat çizgisinde, 4 Hak Mezhebe (Hanefi, Şafii, Maliki, Hanbeli) hakim, ilmi derinliği olan bir fıkıh alimisin.

    --- DAVRANIŞ MODLARI ---
    
    MOD 1: SOHBET (Sadece "Selam, Naber" denirse)
    - "Selamun Aleyküm" denirse: "Ve Aleyküm Selam ve Rahmetullah kıymetli kardeşim." de.
    - "Nasılsın" denirse: "Hamdolsun, hizmetinizdeyiz. Sizler nasılsınız?" de.

    MOD 2: FIKHİ SORULAR (ASIL GÖREV - BU FORMATI KULLAN)
    Eğer kullanıcı dini bir soru sorarsa, aşağıdaki şablonu BİREBİR uygula:

    --- CEVAP ŞABLONU (HTML KULLAN) ---
    
    "Selamun Aleyküm kıymetli kardeşim," (Alt satıra geç)
    "Sorunuzun cevabını Ehl-i Sünnet kaynaklarımız ışığında arz edeyim:"

    <br><br><b>📌 ÖZET HÜKÜM:</b><br>
    (Sorunun cevabını burada net bir cümleyle ver. Örn: "Bu durum abdesti bozar.")

    <br><br><b>📖 DELİLLER VE İZAH:</b><br>
    (Konuyu Ayet ve Hadislerle, fıkhi mantığıyla detaylandır.)

    <br><br><b>⚖️ MEZHEP GÖRÜŞLERİ:</b><br>
    <b>🟦 HANEFİ:</b> [Hüküm ve Detay] (Kaynak: İbn Abidin/Hidaye)<br>
    <b>🟪 ŞAFİİ:</b> [Hüküm ve Detay] (Kaynak: Nevevi/Minhac)<br>
    <b>🟩 MALİKİ:</b> [Hüküm] (Kaynak: Müdevvene)<br>
    <b>🟧 HANBELİ:</b> [Hüküm] (Kaynak: İbn Kudame)<br>

    <br><br><b>⚠️ SONUÇ VE TAVSİYE:</b><br>
    Kıymetli kardeşim, bu bilgiler genel fıkhi kaidelere dayanmaktadır. Durumunuzun özel detayları veya şüpheli noktalar için lütfen sitemizdeki <b>"Soru Sor"</b> butonunu kullanarak veya doğrudan <b>Abdülaziz Güven</b> hocamıza ulaşarak fetva alınız.<br>
    Rabbim ilminizi artırsın. (Amin).

    --- KURALLAR ---
    1. 4 Mezhebi de mutlaka yaz. Bilmiyorsan "Kaynaklarda bu konuda cumhurun görüşü şöyledir" de.
    2. Kaynak isimlerini (Kitap adı) parantez içinde mutlaka belirt.
    3. Üslubun nazik ve kuşatıcı olsun.
    """
    try:
        r = grok_client.chat.completions.create(
            model="grok-3", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": soru}
            ],
            max_tokens=2000, 
            temperature=0.2 
        )
        return r.choices[0].message.content
    except Exception as e:
        logger.error(f"Grok Web Hatası: {e}")
        return "Şu an kaynaklara ulaşmakta güçlük çekiyorum."

# --- DÖNGÜLER VE ROUTES ---

def get_context(tweet):
    if not tweet.referenced_tweets: return None
    for ref in tweet.referenced_tweets:
        if ref.type in ['replied_to', 'quoted']:
            try:
                p = client.get_tweet(ref.id, tweet_fields=["text"])
                if p.data: return p.data.text
            except: pass
    return None

def twitter_loop_thread():
    global ANSWERED_TWEET_IDS, BOT_USERNAME
    logger.info("🚀 Twitter Modülü Başlatıldı...")
    BOT_USERNAME = get_bot_username()

    while True:
        try:
            query = f"@{BOT_USERNAME} -is:retweet -from:{BOT_USERNAME}"
            tweets = client.search_recent_tweets(
                query=query, max_results=20, 
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
                    ctx = get_context(t) if len(raw) < 5 else None

                    logger.info(f"👁️ TWEET: {raw[:30]}...")
                    f = get_fetva_twitter(raw if raw else "Hüküm nedir?", ctx)
                    
                    if f:
                        client.create_tweet(text=f, in_reply_to_tweet_id=t.id)
                        logger.info(f"🚀 CEVAPLANDI: {t.id}")
                        ANSWERED_TWEET_IDS.add(str(t.id))
                        time.sleep(5)
        except Exception as e:
            logger.error(f"Döngü Hatası: {e}")
        time.sleep(200)

@app.route('/', methods=['GET'])
def home():
    return "X Kadısı & Fukaha Botu (Grok-3) Aktif! 🚀"

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

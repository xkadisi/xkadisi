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
# BÖLÜM B: WEB SİTESİ FETVA MANTIĞI (SOHBET + FIKIH)
# =====================================================
def get_fetva_web(soru):
    # GÜNCELLENMİŞ "ESKİ USÜL DETAYLI HOCA" MODU
    system_prompt = """
    KİMLİK:
    Sen "Fukaha Meclisi"nin yapay zeka asistanısın. Ehl-i Sünnet ve'l Cemaat çizgisinde, Hanefi ve Şafii fıkhına hakim, ilmi derinliği olan, nazik ve manevi yönü güçlü bir fıkıh alimisin.

    --- DAVRANIŞ MODLARI ---
    
    MOD 1: SOHBET (Sadece "Selam, Naber" denirse)
    - "Selamun Aleyküm" denirse: "Ve Aleyküm Selam ve Rahmetullah kıymetli kardeşim. Hoş geldiniz." de.
    - "Nasılsın" denirse: "Hamdolsun, Rabbim'e şükürler olsun, hizmetinizdeyiz. Sizler nasılsınız?" de.
    - Sohbet kısmını kısa tut, asıl amacın fetva vermektir.

    MOD 2: FIKHİ SORULAR (ASIL GÖREV - BU FORMATI KULLAN)
    Eğer kullanıcı dini bir soru sorarsa, aşağıdaki "ESKİ VE DETAYLI" şablonu BİREBİR uygula:

    --- CEVAP ŞABLONU (HTML KULLAN) ---
    
    (Giriş Kısmı)
    "Selamun Aleyküm kıymetli kardeşim," (Alt satıra geç)
    "Öncelikle sorunuz için teşekkür ederim. [Konuyla ilgili kısa teşvik edici bir cümle]. Sorunuzun cevabını net bir şekilde vererek başlayayım: [Kısa ve Net Cevap]."

    <br><br><b>Deliller ve İzah:</b><br>
    (Burada konuyu Ayet ve Hadislerle, ilmi bir dille detaylandır. "Efendimiz (s.a.v.) şöyle buyurmuştur..." gibi ifadeler kullan. Fıkhi mantığını açıkla.)

    <br><br><b>Mezhep Farkları:</b><br>
    <b>Hanefi:</b> (Hanefi görüşünü detaylıca anlat.)<br>
    <b>Şafii:</b> (Şafii görüşünü detaylıca anlat.)

    <br><br><b>Sonuç ve Dua:</b><br>
    (Özetle: "Kıymetli kardeşim, özetle durum şudur..." de ve tavsiyeni ver.)
    (Dua ile bitir: "Allah (c.c.), ibadetlerimizi kabul eylesin, bizi rızasına uygun yaşamaya muvaffak kılsın. Amin.")

    --- ÜSLUP KURALLARI ---
    - Robot gibi değil, bir "Mürşit/Hoca" sıcaklığıyla konuş.
    - "Evet/Hayır" diyip geçme. "Zira...", "Çünkü..." diyerek sebebini açıkla.
    - Başlıkları mutlaka <b> (kalın) etiketiyle belirt ki sitede güzel görünsün.
    """
    try:
        r = grok_client.chat.completions.create(
            model="grok-3", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": soru}
            ],
            max_tokens=2000, 
            temperature=0.3 # Hocaefendi üslubu için ideal sıcaklık
        )
        return r.choices[0].message.content
    except Exception as e:
        return "Şu an kaynaklara ulaşmakta güçlük çekiyorum."
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

# -*- coding: utf-8 -*-

import tweepy
from openai import OpenAI
import time
import os
import logging
from requests.exceptions import ConnectionError as RequestsConnectionError
from http.client import RemoteDisconnected

# Logging ayarları - Render logs daha okunaklı olsun
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Key'ler Render Environment Variables'dan çekiliyor
BEARER_TOKEN = os.environ.get("BEARER_TOKEN")
CONSUMER_KEY = os.environ.get("CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("CONSUMER_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")
GROK_API_KEY = os.environ.get("GROK_API_KEY")

# Key kontrol - eksik varsa bot durur
required_keys = [BEARER_TOKEN, CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, GROK_API_KEY]
if any(key is None for key in required_keys):
    logger.error("Eksik API key var! Render Environment Variables'ı kontrol edin.")
    exit(1)

logger.info("Tüm key'ler başarıyla yüklendi.")

# Tweepy client - wait_on_rate_limit=False ile manuel kontrolü biz yapıyoruz
client = tweepy.Client(
    bearer_token=BEARER_TOKEN,
    consumer_key=CONSUMER_KEY,
    consumer_secret=CONSUMER_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET,
    wait_on_rate_limit=False
)

# Grok client
grok_client = OpenAI(
    api_key=GROK_API_KEY,
    base_url="https://api.x.ai/v1"
)

processed_mentions = set()  # Restart'ta sıfırlanır (duplicate önler)

def get_fetva(soru):
    prompt = f"""
Kullanıcı sorusu: {soru}

Dört büyük Sünni mezhebine göre detaylı ama anlaşılır fetva ver.
Her mezhep için hüküm ve kısa kaynak belirt.
Açıklama ekleyebilirsin ama abartma.

Format:

Hanefi: [detaylı hüküm] (el-Hidâye)
Şafiî: [detaylı hüküm] (el-Mecmû')
Mâlikî: [detaylı hüküm] (Muvatta)
Hanbelî: [detaylı hüküm] (el-Muğnî)

Bu genel bilgilendirmedir, mutlak fetva değildir. Lütfen @abdulazizguven'e danışın.

Tüm cevap Türkçe olsun.
"""
    models = ["grok-4", "grok-3", "grok-beta"]  # Sırayla dene (fallback)
    for model in models:
        try:
            response = grok_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.3
            )
            logger.info(f"Grok {model} ile fetva üretildi.")
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Grok {model} hatası: {str(e)}")
    return "Şu anda kaynaklara erişilemedi. Lütfen daha sonra tekrar deneyin."

def cevap_ver():
    logger.info("Mention kontrol ediliyor...")
    backoff_time = 60  # Başlangıç bekleme süresi
    while True:
        try:
            mentions = client.get_users_mentions(
                client.get_me().data.id,
                max_results=3,  # Çok düşük tut, limit'i koru
                tweet_fields=["author_id"]
            )
            backoff_time = 60  # Başarılı olursa sıfırla
            break
        except tweepy.TooManyRequests as e:
            reset = int(e.response.headers.get('x-rate-limit-reset', time.time() + 900))
            wait = max(reset - int(time.time()) + 10, 60)
            logger.warning(f"Rate limit doldu! {wait} saniye bekleniyor...")
            time.sleep(wait)
            return
        except (ConnectionResetError, RequestsConnectionError, RemoteDisconnected, ConnectionAbortedError) as e:
            logger.warning(f"Bağlantı hatası: {e}. {backoff_time} saniye beklenip tekrar denenecek...")
            time.sleep(backoff_time)
            backoff_time = min(backoff_time * 2, 600)  # Exponential backoff, max 10 dakika
        except Exception as e:
            logger.error(f"Beklenmedik mention hatası: {e}")
            time.sleep(120)
            backoff_time = 60

    if not mentions.data:
        logger.info("Yeni mention yok.")
        return

    for mention in mentions.data:
        if mention.id in processed_mentions:
            continue

        soru = mention.text.lower().replace("@xkadisi", "").strip()
        if not soru:
            continue

        logger.info(f"Yeni soru: {soru}")
        fetva = get_fetva(soru)
        cevap = f"Merhaba!\n\n{fetva}"

        try:
            client.create_tweet(text=cevap, in_reply_to_tweet_id=mention.id)
            logger.info("Cevap gönderildi!")
        except tweepy.TooManyRequests as e:
            reset = int(e.response.headers.get('x-rate-limit-reset', time.time() + 900))
            wait = max(reset - int(time.time()) + 10, 60)
            logger.warning(f"Rate limit (tweet atma)! {wait} saniye bekleniyor...")
            time.sleep(wait)
        except (ConnectionResetError, RequestsConnectionError, RemoteDisconnected) as e:
            logger.warning(f"Tweet bağlantı hatası: {e}. 90 saniye bekleniyor...")
            time.sleep(90)
        except Exception as e:
            logger.error(f"Tweet hatası: {e}")

        processed_mentions.add(mention.id)
        time.sleep(30)  # Cevaplar arası güvenli bekleme

logger.info("XKadisi botu BAŞARIYLA başlatıldı! Mention'lar dinleniyor...")
while True:
    cevap_ver()
    time.sleep(300)  # 5 dakika polling (rate limit'i korumak için)

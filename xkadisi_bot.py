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

# Key'ler
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

# Tweepy client
client = tweepy.Client(
    bearer_token=BEARER_TOKEN,
    consumer_key=CONSUMER_KEY,
    consumer_secret=CONSUMER_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET
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

Format:
Hanefi: [hüküm] (el-Hidâye)
Şafiî: [hüküm] (el-Mecmû')
Mâlikî: [hüküm] (Muvatta)
Hanbelî: [hüküm] (el-Muğnî)

Bu genel bilgilendirmedir, mutlak fetva değildir. Lütfen @abdulazizguven'e danışın.
Tüm cevap Türkçe olsun.
"""
    try:
        response = grok_client.chat.completions.create(
            model="grok-4",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Grok hatası: {e}")
        return f"Şu anda fetva üretilemedi: {str(e)}"

def cevap_ver():
    logger.info("Mention kontrol ediliyor...")
    try:
        mentions = client.get_users_mentions(
            client.get_me().data.id,
            max_results=5,  # Rate limit için düşük tut
            tweet_fields=["author_id"]
        )
    except tweepy.TooManyRequests as e:
        reset = int(e.response.headers.get('x-rate-limit-reset', time.time() + 900))
        wait = max(reset - int(time.time()) + 10, 60)
        logger.warning(f"Rate limit! {wait} saniye bekleniyor...")
        time.sleep(wait)
        return
    except (ConnectionResetError, RequestsConnectionError, RemoteDisconnected, ConnectionAbortedError) as e:
        logger.warning(f"Bağlantı kesildi: {e}. 90 saniye beklenip tekrar denenecek...")
        time.sleep(90)
        return
    except Exception as e:
        logger.error(f"Beklenmedik mention hatası: {e}")
        time.sleep(120)
        return

    if not mentions.data:
        logger.info("Yeni mention yok.")
        return

    for mention in mentions.data:
        if mention.id in processed_mentions:
            continue

        try:
            user = client.get_user(id=mention.author_id)
            username = user.data.username if user.data else "biri"
        except Exception as e:
            logger.warning(f"User lookup hatası: {e}")
            username = "biri"

        soru = mention.text.lower().replace("@xkadisi", "").strip()
        if not soru:
            continue

        logger.info(f"Yeni soru: {soru} (@{username})")
        fetva = get_fetva(soru)
        cevap = f"Merhaba!\n\n{fetva}"

        try:
            client.create_tweet(text=cevap, in_reply_to_tweet_id=mention.id)
            logger.info("Cevap gönderildi!")
        except tweepy.TooManyRequests as e:
            logger.warning("Tweet rate limit, 15 dakika bekleniyor...")
            time.sleep(900)
        except (ConnectionResetError, RequestsConnectionError, RemoteDisconnected) as e:
            logger.warning(f"Tweet bağlantı hatası: {e}. 90 saniye bekleniyor...")
            time.sleep(90)
        except Exception as e:
            logger.error(f"Tweet hatası: {e}")

        processed_mentions.add(mention.id)
        time.sleep(10)  # Cevaplar arası güvenli bekleme

logger.info("XKadisi botu BAŞARIYLA başlatıldı! Mention'lar dinleniyor...")
while True:
    cevap_ver()
    time.sleep(120)  # Rate limit için 2 dakika polling

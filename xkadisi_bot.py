# -*- coding: utf-8 -*-

import tweepy
from openai import OpenAI
import time
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Key'ler
BEARER_TOKEN = os.environ.get("BEARER_TOKEN")
CONSUMER_KEY = os.environ.get("CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("CONSUMER_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")
GROK_API_KEY = os.environ.get("GROK_API_KEY")

if not all([BEARER_TOKEN, CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, GROK_API_KEY]):
    logger.error("Eksik API key!")
    exit(1)

logger.info("Tüm key'ler yüklendi.")

client = tweepy.Client(
    bearer_token=BEARER_TOKEN,
    consumer_key=CONSUMER_KEY,
    consumer_secret=CONSUMER_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET
)

grok_client = OpenAI(
    api_key=GROK_API_KEY,
    base_url="https://api.x.ai/v1"
)

processed_mentions = set()

def get_fetva(soru):
    prompt = f"""
Kullanıcı sorusu: {soru}

Dört büyük Sünni mezhebine göre detaylı fetva ver.
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
        return f"Şu anda cevap üretilemedi: {str(e)}"

def cevap_ver():
    logger.info("Mention kontrol ediliyor...")
    try:
        mentions = client.get_users_mentions(
            client.get_me().data.id,
            max_results=2,  # Çok düşük tut, limit'i koru
            tweet_fields=["author_id"]
        )
    except tweepy.TooManyRequests as e:
        reset = int(e.response.headers.get('x-rate-limit-reset', time.time() + 900))
        wait = max(reset - int(time.time()) + 10, 60)
        logger.warning(f"Rate limit! {wait} saniye bekleniyor...")
        time.sleep(wait)
        return
    except Exception as e:
        logger.error(f"Mention hatası: {e}")
        time.sleep(300)  # 5 dakika bekle
        return

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
        except Exception as e:
            logger.error(f"Tweet hatası: {e}")

        processed_mentions.add(mention.id)
        time.sleep(30)  # Cevaplar arası 30 saniye (limit'i koru)

logger.info("XKadisi botu BAŞARIYLA başlatıldı! Mention'lar dinleniyor...")
while True:
    cevap_ver()
    time.sleep(300)  # 5 dakika polling (rate limit'i korumak için)

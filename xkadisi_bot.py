# -*- coding: utf-8 -*-

import tweepy
from openai import OpenAI
import time
import os

# Key'ler Render Environment Variables'dan çekiliyor
BEARER_TOKEN = os.environ.get("BEARER_TOKEN")
CONSUMER_KEY = os.environ.get("CONSUMER_KEY")
CONSUMER_SECRET = os.environ.get("CONSUMER_SECRET")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")
GROK_API_KEY = os.environ.get("GROK_API_KEY")

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

processed_mentions = set()

def get_fetva(soru):
    prompt = f"""
Kullanıcı sorusu: {soru}

Dört büyük Sünni mezhebine göre detaylı ama anlaşılır fetva ver.
Her mezhep için hükmü ve kısa kaynak belirt.
Gerekirse kısa açıklama ekle.

Format:

Hanefi: [detaylı hüküm] (el-Hidâye)
Şafiî: [detaylı hüküm] (el-Mecmû')
Mâlikî: [detaylı hüküm] (Muvatta)
Hanbelî: [detaylı hüküm] (el-Muğnî)

Bu genel bilgilendirmedir, mutlak fetva değildir. Lütfen @abdulazizguven'e danışın.

Tüm cevap Türkçe olsun.
"""
    try:
        response = grok_client.chat.completions.create(
            model="grok-4",  # Erişimin yoksa "grok-3" yap
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Şu anda fetva üretilemedi: {str(e)}"

def cevap_ver():
    global processed_mentions
    print("Mention'lar kontrol ediliyor...")
    try:
        mentions = client.get_users_mentions(
            client.get_me().data.id,
            max_results=10,
            tweet_fields=["author_id"]
        )
    except tweepy.TooManyRequests as e:
        # Dinamik rate limit bekleme
        reset_time = e.response.headers.get("x-rate-limit-reset")
        if reset_time:
            wait = int(reset_time) - int(time.time()) + 10
            print(f"Rate limit doldu, {wait} saniye bekleniyor...")
            time.sleep(wait)
        else:
            print("Rate limit doldu, 15 dakika bekleniyor...")
            time.sleep(900)
        return
    except Exception as e:
        print(f"Mention çekme hatası: {e}")
        time.sleep(60)
        return

    if not mentions.data:
        print("Yeni mention yok.")
        return

    for mention in mentions.data:
        if mention.id in processed_mentions:
            continue

        try:
            user = client.get_user(id=mention.author_id)
            username = user.data.username if user.data else "biri"
        except:
            username = "biri"

        soru = mention.text.lower().replace("@xkadisi", "").strip()
        if not soru:
            print("Boş mention, atlanıyor.")
            processed_mentions.add(mention.id)
            continue

        print(f"Yeni soru: {soru} (@{username})")
        fetva = get_fetva(soru)

        cevap = f"Merhaba!\n\n{fetva}"

        try:
            client.create_tweet(text=cevap, in_reply_to_tweet_id=mention.id)
            print("Uzun cevap gönderildi!\n")
        except tweepy.TooManyRequests as e:
            reset_time = e.response.headers.get("x-rate-limit-reset")
            if reset_time:
                wait = int(reset_time) - int(time.time()) + 10
                print(f"Tweet rate limit, {wait} saniye bekleniyor...")
                time.sleep(wait)
            else:
                print("Tweet rate limit, 15 dakika bekleniyor...")
                time.sleep(900)
        except Exception as e:
            print(f"Tweet gönderme hatası: {e}")

        processed_mentions.add(mention.id)
        time.sleep(5)  # Tweet'ler arası küçük gecikme

print("XKadisi botu başlatıldı! (Rate limit optimize edilmiş versiyon)")
while True:
    cevap_ver()
    time.sleep(90)  # Rate limit'i korumak için 90 saniye bekleme

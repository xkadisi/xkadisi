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

Dört büyük Sünni mezhebine göre ÇOK KISA hüküm ver.
Her mezhep için: Sadece hüküm + parantez içinde klasik kaynak adı.
Maksimum 12-15 kelime/mezhep. Açıklama yazma.

Tam format (başka hiçbir şey ekleme):

Hanefi: [hüküm] (el-Hidâye)
Şafiî: [hüküm] (el-Mecmû')
Mâlikî: [hüküm] (Muvatta)
Hanbelî: [hüküm] (el-Muğnî)

Bu genel bilgilendirmedir, mutlak fetva değildir. Lütfen @abdulazizguven'e danışın.

Tüm cevap Türkçe olsun. Toplam (bu satırlarla birlikte) 230 karakteri geçmesin.
"""
    try:
        response = grok_client.chat.completions.create(
            model="grok-4",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250,
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Şu anda cevap üretilemedi: {str(e)}"

def cevap_ver():
    global processed_mentions
    print("Mention kontrol ediliyor...")
    try:
        mentions = client.get_users_mentions(
            client.get_me().data.id,
            max_results=10,
            tweet_fields=["author_id"]
        )
    except tweepy.TooManyRequests as e:
        print("Rate limit doldu (mention çekme), 15 dakika bekleniyor...")
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

        user = client.get_user(id=mention.author_id)
        username = user.data.username if user.data else "biri"

        soru = mention.text.lower().replace("@xkadisi", "").strip()
        if not soru:
            continue

        print(f"Yeni soru: {soru} (@{username})")
        fetva = get_fetva(soru)

        cevap = f"Merhaba!\n\n{fetva}"

        if len(cevap) > 280:
            cevap = cevap[:277] + "..."

        try:
            client.create_tweet(text=cevap, in_reply_to_tweet_id=mention.id)
            print("Cevap gönderildi!\n")
        except tweepy.TooManyRequests as e:
            print("Rate limit doldu (tweet atma), 15 dakika bekleniyor...")
            time.sleep(900)
        except Exception as e:
            print(f"Tweet atma hatası: {e}")

        processed_mentions.add(mention.id)
        time.sleep(5)

print("XKadisi botu başlatıldı! Mention'lar dinleniyor...")
while True:
    cevap_ver()
    time.sleep(60)

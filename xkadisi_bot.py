# -*- coding: utf-8 -*-

import tweepy
from openai import OpenAI
import time
import os
print("Debug: Key kontrolü başlıyor...")
print("BEARER_TOKEN var mı:", "Evet" if os.environ.get("BEARER_TOKEN") else "Hayır")
print("CONSUMER_KEY var mı:", "Evet" if os.environ.get("CONSUMER_KEY") else "Hayır")
print("GROK_API_KEY var mı:", "Evet" if os.environ.get("GROK_API_KEY") else "Hayır")
print("Tüm key'ler yüklendi mi:", all([
    os.environ.get("BEARER_TOKEN"),
    os.environ.get("CONSUMER_KEY"),
    os.environ.get("CONSUMER_SECRET"),
    os.environ.get("ACCESS_TOKEN"),
    os.environ.get("ACCESS_TOKEN_SECRET"),
    os.environ.get("GROK_API_KEY")
]))
print("Debug tamamlandı, bot başlıyor...")
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

print("Tweepy client oluşturuldu, test ediliyor...")
try:
    me = client.get_me()
    print("Twitter bağlantısı başarılı! Hesap: @" + me.data.username)
except Exception as e:
    print("Twitter bağlantı hatası:", str(e))

# Grok client
grok_client = OpenAI(
    api_key=GROK_API_KEY,
    base_url="https://api.x.ai/v1"
)

print("Grok client oluşturuldu, test ediliyor...")
try:
    test = grok_client.chat.completions.create(
        model="grok-4",
        messages=[{"role": "user", "content": "Merhaba"}],
        max_tokens=5
    )
    print("Grok API bağlantısı başarılı!")
except Exception as e:
    print("Grok API hatası:", str(e))

print("Tüm bağlantılar tamam, bot başlıyor...")

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

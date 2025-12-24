def get_fetva(soru):
    """Grok üzerinden fetva üretir."""
    prompt = f"""
Kullanıcı sorusu: {soru}

Dört büyük Sünni mezhebine göre detaylı fetva ver.
Her mezhep için hüküm ve kısa kaynak belirt.

Format:
Hanefi: [hüküm] (el-Hidâye)
Şafiî: [hüküm] (el-Mecmû')
Mâlikî: [hüküm] (Muvatta)
Hanbelî: [hüküm] (el-Muğnî)

Bu genel bilgilendirmedir, mutlak fetva değildir. Lütfen ehline danışın.
Tüm cevap Türkçe olsun ve 280 karaktere sığmaya çalışsın.
"""
    try:
        response = grok_client.chat.completions.create(
            # --- DÜZELTİLEN KISIM BURASI ---
            model="grok-3",  # Loglarda istenen yeni model ismi
            # -------------------------------
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Grok Hatası: {e}")
        # Hata mesajına zaman ekliyoruz ki Twitter 'Duplicate Content' demesin
        return f"Şu an kaynaklara erişilemiyor. (Hata Kodu: {int(time.time())})"

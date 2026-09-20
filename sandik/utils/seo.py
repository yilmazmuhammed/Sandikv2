"""
Arama motorlarıyla ilgili yardımcılar (canonical adres, yapısal veri, robots.txt, sitemap).

**Neden gerekli:** uygulama birden fazla adresten açılabiliyor — mount noktası
(`www.myilmaz.tr/sandikv2`), alt alan adı (`sandikv2.myilmaz.tr`), yerelde `localhost`.
Aynı sayfanın birkaç adresi olunca arama motoru bunu "kopya içerik" sayar ve hangisini
göstereceğine kendisi karar verir. `<link rel="canonical">` ile asıl adres tek noktadan
bildirilir.

**Asıl adres** `SANDIKv2_SITE_URL` ortam değişkeninden gelir; tanımlı değilse `DEFAULT_SITE_URL`
kullanılır. Uygulama yarın başka bir alan adına taşınırsa (ör. `sandik.com`) yalnızca bu
değişken değiştirilir, şablonlarda hiçbir şey değişmez.

Aynı dosyanın eşi `family_tree/family_tree/utils/seo.py` ve `davetiye/davetiye/utils/seo.py`
içindedir; yalnızca ön ek ve varsayılan adres farklıdır. Birinde düzeltilen hata diğerlerine
de taşınmalıdır.

**`SANDIKv2_SERVER_NAME` ile karıştırılmamalıdır.** O yalnızca `clock.py` içindir: gecelik iş bir
isteğin içinde çalışmadığı için `url_for(_external=True)`nin ihtiyaç duyduğu host adını verir ve
şema/yol taşımaz. Buradaki adres tam adrestir (şema + mount noktası dahil).
"""
import json
import os
from urllib.parse import urlparse

from markupsafe import Markup

# `SANDIKv2_SITE_URL` tanımlı değilken kullanılacak adres. Sitenin bugünkü yayın yeri burasıdır.
DEFAULT_SITE_URL = "https://www.myilmaz.tr/sandikv2"

# Arama sonucunda gösterilen açıklamanın makul üst sınırı. Daha uzunu Google tarafından
# kesilir; kesilen yerden sonrası boşa yazılmış olur.
DESCRIPTION_MAX_LENGTH = 160


def site_url() -> str:
    """Sitenin asıl adresi, sonunda `/` olmadan"""
    return (os.getenv("SANDIKv2_SITE_URL") or DEFAULT_SITE_URL).rstrip("/")


def absolute_url(url=None) -> str:
    """
    Site içi bir adresi (`url_for` çıktısı) asıl adrese göre tam adrese çevirir.

    `url_for` mount noktasında çalışırken ön eki (`/sandikv2`) zaten ekler; asıl adreste de
    aynı ön ek bulunduğu için tekrarlanmaması adına ayıklanır. Alt alan adından gelen istekte
    ön ek yoktur, o zaman ayıklanacak bir şey de olmaz.
    """
    if not url:
        url = "/"
    if url.startswith(("http://", "https://")):
        return url

    base = site_url()
    prefix = urlparse(base).path.rstrip("/")
    if prefix and (url == prefix or url.startswith(prefix + "/")):
        url = url[len(prefix):] or "/"
    return base + url


def canonical_url(path=None) -> str:
    """
    Bu sayfanın asıl adresi.

    `path` verilmezse isteğin kendi yolu kullanılır. Sorgu dizesi (`?sayfa=2` gibi) bilerek
    dışarıda bırakılır: aynı içeriğin süzülmüş hâli ayrı bir sayfa değildir.
    """
    from flask import request

    if path is None:
        try:
            path = request.path
        except RuntimeError:  # istek bağlamı dışında (betikler)
            return site_url()
    return absolute_url(path)


def trim_description(text, max_length=DESCRIPTION_MAX_LENGTH) -> str:
    """Açıklamayı tek satıra indirip sınırı aşarsa kelime ortasından bölmeden kısaltır"""
    text = " ".join((text or "").split())
    if len(text) <= max_length:
        return text
    cut = text[:max_length].rsplit(" ", 1)[0].rstrip(" .,;:")
    return f"{cut}..."


def json_ld(data) -> Markup:
    """
    Yapısal veriyi (schema.org) `<script type="application/ld+json">` olarak gömer.

    `<`, `>` ve `&` kaçırılır: veri kullanıcıdan geliyorsa (sandık adı gibi) içindeki `</script>`
    sayfayı bölebilirdi.
    """
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return Markup(f'<script type="application/ld+json">{text}</script>')


def breadcrumb_ld(items) -> Markup:
    """`[(ad, adres), ...]` listesinden kırıntı gezinme (breadcrumb) yapısal verisi üretir"""
    return json_ld({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": index, "name": name, "item": absolute_url(url)}
            for index, (name, url) in enumerate(items, start=1)
        ],
    })


def faq_ld(questions) -> Markup:
    """
    `[(soru, cevap), ...]` listesinden sıkça sorulan sorular yapısal verisi üretir.

    Cevaplar sayfada görünen metinle **aynı** olmalıdır; Google, sayfada bulunmayan bir cevabı
    yapısal veride görürse sayfayı işaretler.
    """
    return json_ld({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": question,
             "acceptedAnswer": {"@type": "Answer", "text": answer}}
            for question, answer in questions
        ],
    })


def register(flask_app):
    """Şablonların kullandığı yardımcıları Jinja'ya tanıtır"""
    flask_app.jinja_env.globals.update(
        seo_site_url=site_url,
        seo_absolute_url=absolute_url,
        seo_canonical_url=canonical_url,
        seo_json_ld=json_ld,
        seo_breadcrumb_ld=breadcrumb_ld,
        seo_faq_ld=faq_ld,
    )
    return flask_app

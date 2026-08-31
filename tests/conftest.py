"""Pytest kurulumu: izole, bellek-içi bir sqlite veritabanı kurar.

`sandik/utils/db_models.py` import edildiği anda `db.bind()` + `db.generate_mapping()` çalıştırır
(yan etkili import, bkz. Sandikv2/CLAUDE.md "Alan modeli"). Bağlantı ayarı için ortam değişkeni yoktur
(`SANDIKv2_DATABASE_PROVIDER` set edilmemişse dosya yolu `sandik/utils/database.sqlite` olarak
sabittir) — bu yüzden gerçek/geliştirme veritabanına dokunmamak için ilk import'tan *önce*
`Database.bind`'ı yamalayıp bellek-içi bir sqlite'a yönlendiriyoruz. `db_models` yalnızca bu dosya
üzerinden import edilmelidir; başka bir yerden daha önce import edilmişse (örn. `app.py` başka bir
testte çalıştıysa) yama işe yaramaz.

**Şema taşımaları da kapatılır** (`SANDIKv2_AUTO_MIGRATE=0`): `Database.bind` yaması yalnızca Pony'nin
bağlantısını yönlendirir, taşımalar ise `database_target_from_env()` ile **kendi** bağlantısını açar
ve o, geliştiricinin gerçek `database.sqlite` dosyasına giderdi. Testlerde tabloları zaten Pony
sıfırdan kurduğu için taşımalara gerek yoktur.
"""
import os
import sys

import pytest
from pony.orm import Database

SANDIKV2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SANDIKV2_ROOT not in sys.path:
    sys.path.insert(0, SANDIKV2_ROOT)

# Taşımalar kendi bağlantısını açar; bellek-içi veritabanında gerekmez ve açık kalırsa gerçek
# geliştirme veritabanına yazardı. Bkz. modül açıklaması.
os.environ["SANDIKv2_AUTO_MIGRATE"] = "0"

_original_bind = Database.bind
Database.bind = lambda self, *args, **kwargs: _original_bind(self, provider="sqlite", filename=":memory:")
try:
    from sandik.utils import db_models  # noqa: E402  (yan etkili import; sırası kasıtlı)
finally:
    Database.bind = _original_bind


@pytest.fixture(autouse=True)
def _clean_database():
    """Her testten sonra bütün tabloları boşaltır ki testler birbirinden bağımsız kalsın.

    `db_models` süreç başına bir kez import edilebildiği (generate_mapping tekrar çağrılamaz) için
    testler arasında izolasyon "yeni veritabanı" yerine "tabloları temizle" ile sağlanıyor.
    """
    yield
    db_models.db.drop_all_tables(with_all_data=True)
    db_models.db.create_tables()

"""
Uygulanacak şema taşımaları, sırayla.

**Yeni bir taşıma eklerken:**

  * Listenin **sonuna** ekleyin, var olanları değiştirmeyin (uygulanmış taşımalar bir daha
    çalışmaz, geçmişi değiştirmek yalnızca yeni kurulumlarla farklılık yaratır).
  * `name` benzersiz olmalı; sıra numarası + kısa açıklama kalıbı kullanılır.
  * İşlemler kendi kontrollerini yapar (sütun varsa eklemez, tablo yoksa atlar), bu yüzden
    elle müdahale edilmiş veritabanlarında da güvenlidir.
  * `sandik/utils/db_models.py` içindeki modeli de güncellemeyi unutmayın: taşıma var olan
    veritabanlarını, model ise sıfırdan kurulanları belirler. İkisi aynı sonucu vermelidir.
"""
from sandik.utils.migrations import AddColumn, DropColumn, Migration, RunSql  # noqa: F401

MIGRATIONS = []

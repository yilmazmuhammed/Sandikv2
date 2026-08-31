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
from sandik.utils.migrations import AddColumn, Migration, RunSql

MIGRATIONS = [
    Migration(
        name="0001_kullanici_tercihleri",
        description="Kullanıcı tercihleri (ödeme hatırlatma e-postası günleri)",
        operations=[
            # Pony `Json`: mysql/sqlite -> JSON, postgres -> JSONB (bkz. Pony JsonConverter).
            # MySQL JSON sütununa DEFAULT verilemez; oraya NULL eklenip aşağıda dolduruluyor.
            AddColumn("WebUser", "preferences",
                      column_type={"mysql": "JSON NULL", "postgres": "JSONB NOT NULL",
                                   "sqlite": "JSON NOT NULL"},
                      default={"postgres": "'{}'", "sqlite": "'{}'"}),
            # Var olan satırlar boş sözlük alır; `WebUser.get_reminder_days()` eksik anahtarda
            # varsayılana düştüğü için bu, "herkes eskisi gibi mail almaya devam etsin" demektir.
            RunSql("UPDATE `WebUser` SET `preferences` = '{}' WHERE `preferences` IS NULL",
                   description="mevcut kullanıcılara boş tercih yazıldı", only_for="mysql"),
            RunSql("ALTER TABLE `WebUser` MODIFY `preferences` JSON NOT NULL",
                   description="preferences NOT NULL yapıldı", only_for="mysql"),
        ],
    ),
]

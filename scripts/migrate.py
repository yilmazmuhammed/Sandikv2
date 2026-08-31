#!/usr/bin/env python3
"""
Şema taşımalarını elle çalıştırmak / durumu görmek için komut satırı aracı.

Taşımalar uygulama her açıldığında kendiliğinden çalışır (`sandik/utils/db_models.py`); bu araç
yalnızca ne olacağını önceden görmek, durumu incelemek ya da `SANDIKv2_AUTO_MIGRATE='0'` ile otomatik
taşıma kapatıldığında elle uygulamak için gerekir.

    python scripts/migrate.py --durum          # uygulananlar / bekleyenler
    python scripts/migrate.py --kuru-calistir   # ne yapılacağını yazdır
    python scripts/migrate.py                   # uygula

Veritabanı `.env` (FLASK_DEBUG varsa `.env_debug`) dosyasındaki SANDIKv2_DATABASE_* değişkenlerinden
bulunur, yani uygulamanın kullandığı veritabanının aynısıdır.
"""
import os
import sys

from dotenv import load_dotenv

PROJECT_DIRECTORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIRECTORY)

if os.getenv("FLASK_DEBUG"):
    load_dotenv(os.path.join(PROJECT_DIRECTORY, ".env_debug"), override=True)
else:
    load_dotenv(os.path.join(PROJECT_DIRECTORY, ".env"))

from sandik.utils import migrations  # noqa: E402  (.env yüklendikten sonra)


def main():
    dry_run = "--kuru-calistir" in sys.argv
    show_status = "--durum" in sys.argv

    provider, params = migrations.database_target_from_env()
    target = params.get("filename") or params.get("db") or params.get("dsn")
    print(f"Veritabanı: {provider} · {target}\n")

    if show_status:
        applied, pending = migrations.migration_status(provider=provider, params=params)
        print(f"Uygulanmış ({len(applied)}):")
        for migration in applied:
            print(f"  ✓ {migration.name} — {migration.description}")
        print(f"\nBekleyen ({len(pending)}):")
        for migration in pending:
            print(f"  · {migration.name} — {migration.description}")
        return 0

    messages = migrations.run_migrations(provider=provider, params=params, dry_run=dry_run,
                                         log=print)
    if not messages:
        print("Bekleyen taşıma yok.")
    elif dry_run:
        print("\n--kuru-calistir verildi, değişiklik yapılmadı.")
    else:
        print("\nTaşımalar uygulandı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

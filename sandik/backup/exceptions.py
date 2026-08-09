from sandik.utils.exceptions import Sandikv2Exception, THOUSANDS


class BackupException(Sandikv2Exception):
    ERRCODE_THOUSAND = THOUSANDS.BackupException

    def __init__(self, msg="", errcode=1, create_log=False, **kwargs):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log,
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class InconsistentBackupData(BackupException):
    """Yedek dosyasındaki veriler kendi içinde tutarsız. Geri yükleme yapılmaz."""

    def __init__(self, inconsistencies, msg=None, **kwargs):
        self.inconsistencies = inconsistencies
        msg = msg or (f"Yedek dosyasında {len(inconsistencies)} adet tutarsızlık tespit edildi. "
                      f"Yedek YÜKLENMEDİ, veritabanı değiştirilmedi.")
        super().__init__(msg=msg, **kwargs)

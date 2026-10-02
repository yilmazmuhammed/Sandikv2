import os
import subprocess
import sys
from urllib.parse import urljoin

import requests

PROJECT_DIRECTORY_ENV_KEY = "SANDIKv2_PROJECT_DIRECTORY"

# PythonAnywhere web isteklerini 5 dakikada keser; kurulum ondan önce bırakılır ki sayfaya
# "yarıda kaldı" bilgisi dönebilsin.
PIP_INSTALL_TIMEOUT_SECONDS = 240


def _run(command, timeout=None):
    """Komutu çalıştırır; `(çıkış_kodu, çıktı)` döner. Hata çıktısı da aynı metne karışır."""
    try:
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=timeout)
    except FileNotFoundError as e:
        return -1, f"Hata: Komut bulunamadı - {e}"
    except subprocess.TimeoutExpired as e:
        # `text=True` verilse de zaman aşımında çıktı bytes gelebiliyor
        output = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return -1, f"{output}\nHata: İşlem {timeout} saniyede tamamlanamadı. Tekrar deneyiniz."
    return result.returncode, result.stdout


def git_pull(directory=None):
    if directory is None:
        directory = os.getenv(PROJECT_DIRECTORY_ENV_KEY)
    return _run(["git", "-C", directory, "pull"])


def pip_install(directory=None):
    """`requirements.txt`teki bağımlılıkları uygulamanın çalıştığı sanal ortama kurar.

    Kaynak kodu güncellendikten sonra, uygulama yeniden başlatılmadan **önce** çalıştırılır: yeni
    kod yeni bir pakete ihtiyaç duyuyorsa, paket kurulmadan yapılan yeniden başlatma uygulamayı
    açılamaz hâle getirir.
    """
    if directory is None:
        directory = os.getenv(PROJECT_DIRECTORY_ENV_KEY)

    # `sys.executable` kullanılmaz: uWSGI altında python'u değil uwsgi'nin kendisini gösterebilir.
    # `sys.prefix` ise her durumda uygulamanın çalıştığı sanal ortamdır.
    python = os.path.join(sys.prefix, "bin", "python")
    return _run([python, "-m", "pip", "install", "--disable-pip-version-check",
                 "-r", os.path.join(directory, "requirements.txt")],
                timeout=PIP_INSTALL_TIMEOUT_SECONDS)


class PythonAnywhereApi:
    HOST = "www.pythonanywhere.com"

    def __init__(self, token, username, domain=None):
        self._token = token
        self._username = username
        self._domain = domain

        self._base_url = f'https://{self.HOST}/api/v0/user/{self._username}/'
        self._headers = {'Authorization': f'Token {self._token}'}

    def _request(self, method, endpoint):
        url = urljoin(self._base_url, endpoint)
        response = requests.request(
            method=method,
            url=url,
            headers=self._headers
        )
        return response

    def webapp_reload(self, domain=None):
        if domain is None and self._domain is None:
            raise Exception("Domain bilgisi PythonAnywhereApi sınıfının initialize esnasında veya webapp_reload "
                            "fonksiyonu çağrılırken verilmelidir. ")

        domain = domain or self._domain
        return self._request(method="POST", endpoint=f"webapps/{domain}/reload/")

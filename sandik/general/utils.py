import os
from urllib.parse import urljoin

import git
import requests

from sandik.general import db
from sandik.general.exceptions import BankAccountNotFound, PrimaryBankAccountCannotBeDeleted


def remove_bank_account(bank_account_id, deleted_by):
    bank_account = db.get_bank_account(id=bank_account_id)
    if not bank_account:
        raise BankAccountNotFound("Banka hesabı bulunamadı.", create_log=True)

    # if bank_account.is_primary:
    #     raise PrimaryBankAccountCannotBeDeleted("Birincil banka hesabı silinemez.")

    return db.delete_bank_account(bank_account=bank_account, deleted_by=deleted_by)


def git_pull(directory=None):
    if directory is None:
        directory = os.getenv("PROJECT_DIRECTORY")
    ret = git.cmd.Git(directory).pull()
    return ret


class PythonAnywhereApi:
    HOST = "www.pythonanywhere.com"

    def __init__(self, token, username, domain=None):
        self._token = token
        self._username = username
        self._domain = domain

        self._base_url = 'https://{host}/api/v0/user/{username}/'.format(
            host=self.HOST, username=self._username
        )
        self._headers = {'Authorization': 'Token {token}'.format(token=self._token)}

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

import base64
import time
from urllib.parse import urlencode

import requests


class OAuth2Client:

    def __init__(
            self, client_id, client_secret, environment,
            private_key_file=None, private_key_data=None,
            redirect_uri=None, scope=""
    ):
        if environment not in self.ENVIRONMENTS:
            raise ValueError(f"Environment must be one of: {self.ENVIRONMENTS.keys()}")

        if private_key_file and private_key_data:
            raise ValueError("Hem private_key_file hem de private_key_data aynı anda verilemez.")

        self.client_id = client_id
        self.client_secret = client_secret
        self.environment = environment
        self.redirect_uri = redirect_uri
        self.scope = scope

        self.identity_url = self.ENVIRONMENTS[environment]["identity"]
        self.gateway_url = self.ENVIRONMENTS[environment]["gateway"]
        self.token_url = f"{self.identity_url}/connect/token"
        self.auth_url = f"{self.identity_url}/connect/authorize"

        self.access_token = None
        self.refresh_token = None
        self.expires_at = None

        self.signature = None
        if private_key_file:
            self.signature = self._load_signature_from_file(private_key_file)
        elif private_key_data:
            self.signature = self._prepare_signature_from_data(private_key_data)

    def _load_signature_from_file(self, path):
        with open(path, 'r') as f:
            content = f.read()
        return self._prepare_signature_from_data(content)

    def _prepare_signature_from_data(self, key_data):
        clean = self._clean_pem(key_data)
        return self._base64_encode(clean)

    def _clean_pem(self, pem_str):
        lines = pem_str.strip().splitlines()
        lines = [line for line in lines if not line.startswith("-----")]
        return "\n".join(lines).strip()

    def _base64_encode(self, text):
        return base64.b64encode(text.encode()).decode()

    def is_token_expired(self):
        return self.expires_at is None or time.time() > self.expires_at

    def fetch_token_client_credentials(self, scope=None):
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': scope or self.scope
        }
        response = requests.post(self.token_url, data=data)
        response.raise_for_status()
        token_data = response.json()
        self._store_token_data(token_data)

    def fetch_token_authorization_code(self, code):
        if not self.redirect_uri:
            raise ValueError("redirect_uri belirtilmelidir.")
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.redirect_uri,
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        response = requests.post(self.token_url, data=data)
        response.raise_for_status()
        token_data = response.json()
        self._store_token_data(token_data)

    def get_authorization_url(self, state="xyz"):
        if not self.redirect_uri:
            raise ValueError("redirect_uri belirtilmelidir.")
        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': self.scope,
            'state': state
        }
        return f"{self.auth_url}?{urlencode(params)}"

    def refresh_access_token(self):
        if not self.refresh_token:
            raise RuntimeError("Refresh token is not available.")
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        response = requests.post(self.token_url, data=data)
        response.raise_for_status()
        token_data = response.json()
        self._store_token_data(token_data)

    def _store_token_data(self, token_data):
        print("store_token:", token_data)
        self.access_token = token_data['access_token']
        self.refresh_token = token_data.get('refresh_token', self.refresh_token)
        expires_in = token_data.get('expires_in', 3600)
        self.expires_at = time.time() + expires_in

    def get_headers(self):
        if self.is_token_expired():
            if self.refresh_token:
                print("Access token expired. Refreshing...")
                self.refresh_access_token()
            else:
                raise RuntimeError("Token expired or not fetched yet.")
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        if self.signature:
            headers['Signature'] = self.signature
        return headers

    def api_get(self, endpoint, params=None):
        url = f"{self.gateway_url}{endpoint}"
        headers = self.get_headers()
        response = requests.get(url, headers=headers, params=params)
        # response.raise_for_status()
        return response.json()

    def api_post(self, endpoint, data=None, json=None):
        url = f"{self.gateway_url}{endpoint}"
        headers = self.get_headers()
        response = requests.post(url, headers=headers, data=data, json=json)
        # response.raise_for_status()
        return response.json()


class KtApiAppType:
    TEST = "test"
    PREP = "prep"
    PROD = "prod"


class KtApi(OAuth2Client):
    ENVIRONMENTS = {
        KtApiAppType.TEST: {
            'identity': "https://test-identity.kuveytturk.com.tr",
            'gateway': "https://test-gateway.kuveytturk.com.tr"
        },
        KtApiAppType.PREP: {
            'identity': "https://prep-identity.kuveytturk.com.tr",
            'gateway': "https://prep-gateway.kuveytturk.com.tr"
        },
        KtApiAppType.PROD: {
            'identity': "https://identity.kuveytturk.com.tr",
            'gateway': "https://gateway.kuveytturk.com.tr"
        },
    }

    def url_for_access_token_with_authorization_code_flow(self, state=""):
        """
        :param state: Optional, but strongly recommended. Identity server will echo back the state value on the token
        response, this is for round tripping state between client and provider, correlating request and response and
        CSRF/replay protection.
        :return:
        """
        response_type = "code"

        return (f"{self.identity_address}/connect/authorize"
                f"?response_type={response_type}"
                f"&state={state}"
                f"&client_id={self._client_id}"
                f"&scope={self._scope}"
                f"&redirect_uri={self._redirect_uri}")


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", '.env_debug'), override=True)

    scope = "loans payments digital_payments donations accounts cards transfers public crm api"
    redirect_uri = "http://myilmaz.local:5000/sandikv2/kt/callback"

    client = KtApi(
        client_id=os.getenv('SANDIKv2_KT_CLIENT_ID'),
        client_secret=os.getenv('SANDIKv2_KT_CLIENT_SECRET'),
        environment="prep",
        redirect_uri=redirect_uri,
        scope=scope,
        private_key_file="a.txt"
    )

    # Kullanıcıyı yönlendir:
    print("Autgorization code almak için aşağıdaki linke tıklayın. Açılan sayfadan giriş yapın ve dönüş url'sindeki "
          "'code' değerini Authorization code olarak saklayınız:")
    print(client.get_authorization_url())

    # Yetkilendirme sonrası callback'e gelen kod ile token al
    code = input("Authorization code girin: ")
    if code:
        client.fetch_token_authorization_code(code)

    client.fetch_token_client_credentials()

    # Artık istek yapabilirsin
    print(client.api_get("/v1/data/testCustomers"))

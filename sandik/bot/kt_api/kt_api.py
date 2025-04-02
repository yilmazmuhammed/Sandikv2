class KtAppType:
    TEST = "test"
    PREP = "prep"
    PROD = "prod"


class KtApi:
    TEST_IDENTITY_ADDRESS = "https://test-identity.kuveytturk.com.tr"
    PREP_IDENTITY_ADDRESS = "https://prep-identity.kuveytturk.com.tr"
    PROD_IDENTITY_ADDRESS = "https://identity.kuveytturk.com.tr"
    TEST_GATEWAY_ADDRESS = "https://test-gateway.kuveytturk.com.tr"
    PREP_GATEWAY_ADDRESS = "https://prep-gateway.kuveytturk.com.tr"
    PROD_GATEWAY_ADDRESS = "https://gateway.kuveytturk.com.tr"

    def __init__(self, application_type, client_id, redirect_uri, scope="accounts"):
        self._client_id = client_id
        self._redirect_uri = redirect_uri
        self._scope = scope
        self._application_type = application_type

        if self._application_type == KtAppType.PREP:
            self.identity_address = self.PREP_IDENTITY_ADDRESS
        elif self._application_type == KtAppType.PROD:
            self.identity_address = self.PROD_IDENTITY_ADDRESS
        elif self._application_type == KtAppType.TEST:
            self.identity_address = self.TEST_IDENTITY_ADDRESS
        else:
            raise ValueError("Application type must be either TEST, PREP or PROD")

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


if __name__ == '__main__':
    import webbrowser
    import http.server
    import socket
    import socketserver
    import threading


    def find_free_port(server_ip):
        """Boş bir port bulup döndürür."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((server_ip, 0))
            _, port = s.getsockname()
        return port


    def get_redirected_url(login_url: str, server: tuple[str, int]) -> str:
        """Varsayılan tarayıcıda giriş sayfasını açar ve yönlendirilmiş URL'yi yakalar."""

        redirected_url = None  # Yakalanan URL burada saklanacak

        class RedirectHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                nonlocal redirected_url
                redirected_url = self.path
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"Giris basarili, bu pencereyi kapatabilirsiniz.")
                threading.Thread(target=httpd.shutdown).start()  # Sunucuyu kapat

        # HTTP sunucusunu başlat
        with socketserver.TCPServer(server, RedirectHandler) as httpd:
            print(f"Yerel sunucu {server} adresinde çalışıyor...")

            # Tarayıcıda giriş sayfasını aç
            webbrowser.open(login_url)

            # Sunucuyu engellemeyen bir şekilde çalıştır
            httpd.serve_forever()

        return redirected_url


    # Kullanım örneği:
    localhost = "localhost"
    # port = find_free_port(localhost)  # Dinamik port almak için
    port = 5050
    redirect_uri = f"http://{localhost}:{port}/callback"

    client_id = ""
    kt_api = KtApi(client_id=client_id, redirect_uri=redirect_uri, application_type=KtAppType.PREP)

    login_url = kt_api.url_for_access_token_with_authorization_code_flow()

    redirected_url = get_redirected_url(login_url=login_url, server=(localhost, port))
    print("Dönüş URL'si:", redirected_url)

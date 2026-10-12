"""Serveur de développement du front : aucun cache (le navigateur recharge toujours la dernière version)
et repli sur index.html pour les adresses comme /admin. Usage : python3 serve.py [port]"""
import http.server
import os
import socket
import sys


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def send_head(self):
        url_path = self.path.split("?", 1)[0]
        if not os.path.exists(self.translate_path(url_path)) and "." not in os.path.basename(url_path):
            self.path = "/index.html"  # adresse « logique » de l'application (ex. /admin)
        return super().send_head()


class Server(http.server.ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self):  # accepte localhost en IPv4 et IPv6
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5173
    Server(("::", port), Handler).serve_forever()

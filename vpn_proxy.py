#!/usr/bin/env python3
"""
Простой HTTP/HTTPS прокси для перенаправления трафика через VPN туннель в vpnspace.
Запускается на хосте и слушает на 0.0.0.0:9999, перенаправляя запросы через vpnspace.
"""

import http.server
import socketserver
import urllib.request
import ssl
import sys
import subprocess
import json

PORT = 9999

class VPNProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.forward_request(method='GET')
    
    def do_POST(self):
        self.forward_request(method='POST')
    
    def forward_request(self, method):
        """Перенаправить запрос через VPN namespace"""
        url = f"https://api.telegram.org{self.path}"
        
        # Получаем тело запроса если POST
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b''
        
        try:
            # Используем curl через vpnspace для обхода блокировок
            cmd = [
                'sudo', 'ip', 'netns', 'exec', 'vpnspace',
                'curl', '-s', '-w', '\n%{http_code}',
                '-X', method,
                '--connect-timeout', '10',
                '--max-time', '30',
            ]
            
            # Добавляем заголовки
            for header, value in self.headers.items():
                if header.lower() not in ['host', 'connection', 'content-length']:
                    cmd.extend(['-H', f'{header}: {value}'])
            
            # Добавляем данные для POST
            if body:
                cmd.extend(['-d', body.decode('utf-8', errors='ignore')])
            
            cmd.append(url)
            
            result = subprocess.run(cmd, capture_output=True, timeout=35)
            output = result.stdout.decode('utf-8', errors='ignore')
            
            # Парсим ответ curl
            lines = output.strip().split('\n')
            status_code = int(lines[-1]) if lines[-1].isdigit() else 500
            response_body = '\n'.join(lines[:-1])
            
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response_body)))
            self.end_headers()
            
            self.wfile.write(response_body.encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(f"Proxy error: {e}".encode())
    
    def log_message(self, format, *args):
        print(f"[VPN PROXY] {format % args}", file=sys.stderr)

if __name__ == '__main__':
    Handler = VPNProxyHandler
    httpd = socketserver.TCPServer(("0.0.0.0", PORT), Handler)
    print(f"VPN Proxy запущен на 0.0.0.0:{PORT}")
    sys.stdout.flush()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nVPN Proxy остановлен")
        sys.exit(0)

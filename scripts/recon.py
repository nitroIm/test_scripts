import sys
import os
import socket
import ssl
import requests
import dns.resolver
import concurrent.futures
import whois
from datetime import datetime

# Отключаем предупреждения SSL
requests.packages.urllib3.disable_warnings()

def clean_domain(target):
    target = target.replace("https://", "").replace("http://", "").replace("www.", "")
    return target.split("/")[0]

def get_dns_records(domain):
    print(f"\n[+] DNS Разведка")
    records = {}
    for record_type in ['A', 'MX', 'NS', 'TXT', 'CNAME']:
        try:
            answers = dns.resolver.resolve(domain, record_type)
            records[record_type] = [str(rdata) for rdata in answers]
            print(f"  - {record_type}: {records[record_type]}")
        except Exception:
            pass

def check_port(ip, port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            if s.connect_ex((ip, port)) == 0:
                return port
    except:
        pass
    return None

def scan_ports(ip):
    ports = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 8080, 8443]
    print(f"\n[+] Сканирование портов (IP: {ip})")
    open_ports = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(lambda p: check_port(ip, p), ports)
        for port in results:
            if port:
                open_ports.append(port)
                print(f"  - Порт {port}: ОТКРЫТ")
    if not open_ports:
        print("  - Открытых стандартных портов не найдено.")

def get_ssl_info(domain):
    print(f"\n[+] SSL/TLS Сертификат")
    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                issuer = dict(x[0] for x in cert['issuer']).get('organizationName', 'N/A')
                print(f"  - Издатель: {issuer}")
                print(f"  - Действителен до: {cert['notAfter']}")
    except Exception as e:
        print(f"  - Ошибка получения SSL: {e}")

def check_headers_and_waf(domain):
    print(f"\n[+] HTTP Заголовки и WAF")
    headers_sent = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(f"https://{domain}", headers=headers_sent, timeout=10, verify=False)
        print(f"  - HTTP Статус: {resp.status_code}")
        
        # Заголовки безопасности
        sec_headers = ["Strict-Transport-Security", "Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options"]
        for h in sec_headers:
            val = resp.headers.get(h)
            status = "✅ Есть" if val else "❌ НЕТ"
            print(f"  - {h}: {status}")
            
        # Определение WAF
        waf_sigs = ["cloudflare", "variti", "akamai", "sucuri", "imperva", "f5", "ddos-guard"]
        server = str(resp.headers.get("Server", "")).lower()
        body = resp.text[:2000].lower()
        headers_str = str(resp.headers).lower()
        
        detected_waf = False
        for waf in waf_sigs:
            if waf in server or waf in body or waf in headers_str:
                print(f"  - ⚠️ Обнаружен WAF: {waf.upper()}")
                detected_waf = True
        if not detected_waf:
            print("  - WAF не обнаружен (или скрыт).")
            
        print(f"  - Server: {resp.headers.get('Server', 'Скрыт')}")
    except Exception as e:
        print(f"  - Ошибка запроса: {e}")

def get_whois(domain):
    print(f"\n[+] WHOIS Информация")
    try:
        w = whois.whois(domain)
        print(f"  - Регистратор: {w.registrar}")
        print(f"  - Дата создания: {w.creation_date}")
        print(f"  - Дата окончания: {w.expiration_date}")
        print(f"  - Страна: {w.country}")
    except Exception as e:
        print(f"  - Ошибка WHOIS: {e}")

if __name__ == "__main__":
    target = os.environ.get("TARGET_URL", "ozon.ru")
    domain = clean_domain(target)
    
    print(f"=== НАЧАЛО РАЗВЕДКИ: {domain} ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")
    
    get_whois(domain)
    get_dns_records(domain)
    
    try:
        ip = socket.gethostbyname(domain)
        print(f"\n[+] IP-адрес: {ip}")
        scan_ports(ip)
    except Exception as e:
        print(f"Ошибка получения IP: {e}")

    get_ssl_info(domain)
    check_headers_and_waf(domain)
    
    print("\n=== РАЗВЕДКА ЗАВЕРШЕНА ===")
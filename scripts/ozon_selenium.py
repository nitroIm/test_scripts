from seleniumbase import SB
from bs4 import BeautifulSoup
import json
import re
import time

def parse_ozon_product(url: str):
    # SeleniumBase с CDP-режимом — самый надежный способ обхода защиты Ozon
    with SB(uc=True, headless=True) as sb:
        try:
            # Открываем страницу в невидимом режиме с обходом детекта
            sb.uc_open_with_reconnect(url, reconnect_time=4)
            
            # Ждем загрузки ключевого элемента
            sb.wait_for_element("div[data-widget='webPrice']", timeout=30)
            time.sleep(3) # Даем время на подгрузку динамики

            html = sb.get_page_source()
            soup = BeautifulSoup(html, "html.parser")

            # Извлечение данных
            title_tag = soup.find("h1")
            name = title_tag.get_text(strip=True) if title_tag else "Название не найдено"

            price_block = soup.find("div", {"data-widget": "webPrice"})
            price = "Цена не найдена"
            if price_block:
                price_text = price_block.get_text(" ", strip=True)
                match = re.search(r"(\d[\d\s]*)\s*₽", price_text)
                if match:
                    price = match.group(0).strip()

            img_tag = soup.find("img", {"data-widget": "webGallery"})
            image_url = img_tag["src"] if img_tag and img_tag.has_attr("src") else "Картинка не найдена"
            
            if image_url == "Картинка не найдена":
                json_ld = soup.find("script", {"type": "application/ld+json"})
                if json_ld:
                    try:
                        data = json.loads(json_ld.string)
                        if isinstance(data, list):
                            data = data[0]
                        image_url = data.get("image", image_url)
                    except Exception:
                        pass

            result = {
                "url": url,
                "name": name,
                "price": price,
                "image": image_url
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return result

        except Exception as e:
            print(f"Ошибка при парсинге {url}: {e}")
            return None

if __name__ == "__main__":
    test_url = "https://www.ozon.ru/product/1156624388/" 
    parse_ozon_product(test_url)
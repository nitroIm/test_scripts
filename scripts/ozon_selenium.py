import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth
from bs4 import BeautifulSoup
import json
import re
import time

def parse_ozon_product(url: str):
    options = uc.ChromeOptions()
    # Убираем headless, запустим через xvfb
    # options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    # use_subprocess=False часто решает проблему с подключением
    driver = uc.Chrome(options=options, use_subprocess=False)

    stealth(driver,
            languages=["ru-RU", "ru"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True)

    try:
        driver.get(url)
        # Увеличиваем таймаут ожидания, так как сайт тяжелый
        WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-widget='webPrice']"))
        )
        
        # Небольшая пауза для подгрузки динамики
        time.sleep(2) 
        
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        # --- Извлечение данных ---
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
    finally:
        driver.quit()

if __name__ == "__main__":
    # Ссылка на любой товар Ozon
    test_url = "https://www.ozon.ru/product/1156624388/" 
    parse_ozon_product(test_url)
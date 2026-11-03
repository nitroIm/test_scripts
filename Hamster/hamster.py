import asyncio
import os
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        print("Запускаем браузер...")
        browser = await p.chromium.launch(headless=True)
        
        context = await browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
        )
        page = await context.new_page()

        print("Открываем Telegram Web...")
        await page.goto("https://web.telegram.org/k/")
        
        print("Ждем загрузки...")
        await page.wait_for_timeout(10000) 

        print("Делаем скриншот...")
        await page.screenshot(path="Hamster/telegram_web.png")
        
        print("Готово.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
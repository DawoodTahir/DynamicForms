import numpy as np
import asyncio
import os
from utils import DynamicWeb
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv('.env')  # Load environment variables from .env file in current directory

api_key=os.environ.get("OPENAI_API_KEY")
cap_key=os.environ.get("CAP_API")
async def run():
    file ='uploads/file_A.xlsx'

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--ignore-ssl-errors',
                '--ignore-certificate-errors',
                '--ignore-certificate-errors-spki-list',
                '--ignore-ssl-errors-spki-list',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ]
        )
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()
        ##crearte an instance of our class DynamicWeb
        pipe = DynamicWeb(cap_key, api_key)
        urls=pipe.ingestion(file)
        # for url in urls:
        url="https://www.arsroofing.net/"
        try:
                print(f"[🌐] Navigating to {url}")
                await page.goto(url)
                await page.wait_for_load_state("networkidle") ##waits for page to become fully loaded

                await pipe.process_page(page, url) ##fill the form right away, or by going to form page and filling up 

            
        except Exception as e:
            print(f"[!] Error processing URL {url}: {str(e)}")
            return False

    await browser.close()

asyncio.run(run())
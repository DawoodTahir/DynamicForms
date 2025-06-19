import numpy as np
import asyncio
from utils import DynamicWeb
from playwright.async_api import async_playwright


async def run():
    file ='file_A.xlsx'

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        ##crearte an instance of our class DynamicWeb
        pipe=DynamicWeb()
        urls=pipe.ingestion(file)
        # for url in urls:
        url="https://www.stonecreekcontractors.com/"
        try:
                print(f"[🌐] Navigating to {url}")
                await page.goto(url)
                await page.wait_for_load_state("networkidle") ##waits for page to become fully loaded

                await pipe.process_page(page, url) ##fill the form right away, or by going to form page and filling up 

                # # --- Handle reCAPTCHA ---
                # print("[🤖] Waiting for CAPTCHA to load...")
                # captcha_selectors = [
                #     'iframe[title="reCAPTCHA"]',
                #     'iframe[src*="recaptcha"]',
                #     '.g-recaptcha',
                #     'iframe[title*="recaptcha"]'
                # ]
                
                # for selector in captcha_selectors:
                #     if await page.locator(selector).count() > 0:
                #         print(f"Found CAPTCHA with selector: {selector}")
                #         captcha = selector
                #         # Get the main reCAPTCHA iframe
                #         recaptcha_frame = page.frame_locator(captcha)
                        
                #         # Click the checkbox in the main iframe
                #         await recaptcha_frame.locator('.recaptcha-checkbox-border').click()

                #         site_key = pipe.site_key(url)
                #         solver = pipe.Captcha_solver(site_key, url)
                        
                #         # Put the solved captcha in form 
                #         await page.evaluate(f'''
                #             document.querySelector("textarea[name='g-recaptcha-response']").style.display = 'block';
                #             document.querySelector("textarea[name='g-recaptcha-response']").value = "{solver}";
                #         ''')
                #         break
                # else:
                #     print("No CAPTCHA found on page")
                
                # # Submit form and verify submission using sentiment analyzer
                # if await pipe.submit_form('input[type="submit"]', page):
                #     print("[🚀] Form submitted successfully!")
                # else:
                #     print("[!] Form submission failed or could not be verified")
                #     pass

        except Exception as e:
            print(f"[!] Error processing URL {url}: {str(e)}")
            return False

    await browser.close()

asyncio.run(run())
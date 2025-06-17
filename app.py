import os
from quart import Quart, request, jsonify, render_template
from werkzeug.utils import secure_filename
from playwright.async_api import async_playwright
from utils import DynamicWeb,Agent

app = Quart(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/', methods=['GET'])
async def home():
    return await render_template('index.html')  # HTML form lives here

@app.route('/process', methods=['POST'])
async def process_url():
    try:
        data = await request.get_json()
        url = data.get('url')
        if not url:
            return jsonify({"error": "Missing URL"}), 400

        result = await run_playwright(url)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

async def run_playwright(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        agent = Agent('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', role="email_orchestrator", system_prompt="You are an email generator for our business , that takes email and contact name to return subject and email content and send it")
        page = await context.new_page()

        pipe = DynamicWeb()

        try:
            print(f"[🌐] Navigating to {url}")
            await page.goto(url)
            await page.wait_for_load_state("networkidle")

            # # First check for "protected by CAPTCHA" messages
            # captcha_message_selectors = [
            #     'text="protected by CAPTCHA"',
            #     'text="protected by reCAPTCHA"',
            #     'text="protected by captcha"',
            #     '[class*="captcha-protected"]',
            #     '[id*="captcha-protected"]'
            # ]

            # for selector in captcha_message_selectors:
            #     try:
            #         if await page.locator(selector).count() > 0:
            #             print(f"[!] Site is protected by CAPTCHA: {selector}")
            #             return {"status": "error", "message": "Site is protected by CAPTCHA and cannot be automated"}
            #     except Exception:
            #         continue

            # # CAPTCHA detection
            # captcha_selectors = [
            #     'iframe[title="reCAPTCHA"]',
            #     'iframe[src*="recaptcha"]',
            #     '.g-recaptcha',
            #     'iframe[title*="recaptcha"]'
            # ]

            # for selector in captcha_selectors:
            #     try:
            #         if await page.locator(selector).count() > 0:
            #             print(f"[🤖] reCAPTCHA detected: {selector}")
                        
            #             # Get site key using the existing method
            #             site_key = await pipe.site_key(url)
            #             if not site_key:
            #                 print("[!] Could not find site key")
            #                 continue

            #             print(f"[🔑] Found site key: {site_key}")
                        
            #             # Solve CAPTCHA
            #             solver = pipe.Captcha_solver(site_key, url)
            #             if not solver:
            #                 print("[!] Failed to solve CAPTCHA")
            #                 continue

            #             # Set the response
            #             await page.evaluate(f'''
            #                 document.querySelector("textarea[name='g-recaptcha-response']").style.display = 'block';
            #                 document.querySelector("textarea[name='g-recaptcha-response']").value = "{solver}";
            #             ''')
            #             print("[✓] CAPTCHA response set")
            #             break
            #     except Exception as e:
            #         print(f"[!] Error handling reCAPTCHA: {str(e)}")
            #         continue

            # Process the page after CAPTCHA handling
            result= await pipe.process_page(page, url)
            if not result:
                await agent.send_email(
                recipient_email="client@example.com",
                recipient_name="Client Name",
                url=url,
                agent=agent,
                gmail_creds='12345'
                )
                return {"status": "error", "message": "Form submission failed and client was notified."}
            else:
                return {"status": "success", "message": "Form submitted"}

        except Exception as e:
            print(f"[!] Error in run_playwright: {str(e)}")
            return {"status": "error", "message": str(e)}
        finally:
            await browser.close()

if __name__ == '__main__':
    app.run(debug=True)

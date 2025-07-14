import os
from dotenv import load_dotenv
from quart import Quart, request, jsonify, render_template
from werkzeug.utils import secure_filename
from playwright.async_api import async_playwright
from utils import DynamicWeb,Agent

app = Quart(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

load_dotenv('.env')  # Load environment variables from .env file in current directory

api_key=os.environ.get("OPENAI_API_KEY")
cap_key=os.environ.get("CAP_API")

@app.route('/', methods=['GET'])
async def home():
    return await render_template('index.html')  # HTML form lives here

@app.route('/process', methods=['POST'])
async def process_url():
    try:
        data = await request.get_json()
        print(data)
        url = data.get('url')
        user_data = data.get('userData')  # <-- get userData from frontend
        if not url:
            return jsonify({"error": "Missing URL"}), 400

        result = await run_playwright(url, user_data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

async def run_playwright(url, user_data=None):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--ignore-ssl-errors',
                '--ignore-certificate-errors',
                '--ignore-certificate-errors-spki-list',
                '--ignore-ssl-errors-spki-list',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--single-process'
            ]
        )
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        pipe = DynamicWeb(cap_key, api_key, user_data=user_data)  # <-- pass user_data

        try:
            print(f"[🌐] Navigating to {url}")
            await page.goto(url)
            await page.wait_for_load_state("networkidle")

            # Process the page after CAPTCHA handling
            result = await pipe.process_page(page, url)
            return result
            

        except Exception as e:
            print(f"[!] Error in run_playwright: {str(e)}")
            return {"status": "error", "message": str(e)}
        finally:
            await browser.close()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

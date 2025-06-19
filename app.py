import os
from quart import Quart, request, jsonify, render_template
from werkzeug.utils import secure_filename
from playwright.async_api import async_playwright
from utils import DynamicWeb,Agent

app = Quart(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
api_key=os.environ.get("OPENAI_API_KEY")
cap_key=os.environ.get("CAP_API")

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
        agent = Agent(api_key, role="email_orchestrator", system_prompt="You are an email generator for our business , that takes email and contact name to return subject and email content and send it")
        page = await context.new_page()

        pipe = DynamicWeb(api_key,cap_key)

        try:
            print(f"[🌐] Navigating to {url}")
            await page.goto(url)
            await page.wait_for_load_state("networkidle")

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
                return {"status": "error", "message": "Couldn't Resolve Form, Hence Sent Email instead."}
            else:
                return {"status": "success", "message": "Form submitted"}

        except Exception as e:
            print(f"[!] Error in run_playwright: {str(e)}")
            return {"status": "error", "message": str(e)}
        finally:
            await browser.close()

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)

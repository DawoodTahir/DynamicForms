import pandas as pd
from io import BytesIO
import requests
from playwright.async_api import async_playwright
import time
import re
import openai
from typing import Optional, Dict, Any, List
import json
import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


class Agent:
    def __init__(self, api_key: str, role: str, system_prompt: str):
        self.api_key = api_key
        self.role = role
        self.system_prompt = system_prompt
        self.client = openai.OpenAI(api_key=api_key)

    async def analyze(self, content: str, additional_context: Optional[Dict] = None) -> Dict[str, Any]:
        try:
            prompt = f"""
            Content to analyze:
            {content}
            
            Additional context (if any):
            {json.dumps(additional_context) if additional_context else 'None'}
            
            Please analyze the content and respond with a valid JSON object containing:
            - status: "success" or "error" or "unknown"
            - confidence: number between 0-100
            - message: the main message found
            - reasoning: brief explanation
            """

            # OpenAI's client is not async, so we don't await it
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                response_format={ "type": "json_object" }  # Force JSON response
            )

            analysis_text = response.choices[0].message.content
            if not analysis_text:
                raise ValueError("Empty response from API")

            try:
                analysis = json.loads(analysis_text)
            except json.JSONDecodeError as e:
                print(f"[!] Failed to parse JSON response: {analysis_text}")
                raise ValueError(f"Invalid JSON response: {str(e)}")

            # Ensure all required fields are present
            required_fields = ["status", "confidence", "message", "reasoning"]
            for field in required_fields:
                if field not in analysis:
                    analysis[field] = "unknown" if field == "status" else 0 if field == "confidence" else ""

            return analysis

        except Exception as e:
            print(f"[!] Error in {self.role} analysis: {str(e)}")
            return {
                "status": "error",
                "confidence": 0,
                "message": str(e),
                "reasoning": "Error occurred during analysis"
            }
    async def send_email(self, recipient_email, recipient_name, url, agent, gmail_creds: Credentials):
            
            # 1. Use the agent to generate subject and body
            subject, body = await agent.send_email(recipient_name, url)
            
            # 2. Create the email message
            message = MIMEText(body, "plain")
            message['to'] = recipient_email
            message['from'] = "me"
            message['subject'] = subject

            # 3. Encode the message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            # 4. Send the email using Gmail API
            try:
                service = build('gmail', 'v1', credentials=gmail_creds)
                send_message = service.users().messages().send(userId="me", body={'raw': raw_message}).execute()
                print(f"[✓] Email sent to {recipient_email}: {send_message['id']}")
                return send_message
            except Exception as e:
                print(f"[!] Failed to send email: {e}")
                return None

class FormAnalyzer:
    def __init__(self, api_key: str):
        self.api_key = api_key
        
        self.sentiment_agent = Agent(
            api_key=api_key,
            role="sentiment_analyzer",
            system_prompt="""You are a form submission response analyzer. 
            Analyze the content and determine if it's a success or error message.
            Respond in JSON format:
            {
                "status": "success" or "error" or "unknown",
                "confidence": number between 0-100,
                "message": "main message found",
                "reasoning": "brief explanation"
            }"""
        )

        self.radio_agent = Agent(
            api_key=api_key,
            role="radio_selector",
            system_prompt="""You are a form field analyzer specializing in radio button selection.
            Given a list of radio button options, select the most appropriate one based on these guidelines:
            1. Prefer options that indicate interest in services
            2. Avoid options that indicate "other" or "none"
            3. Choose options that suggest active engagement
            Respond in JSON format:
            {
                "selected_option": "the chosen option",
                "confidence": number between 0-100,
                "reasoning": "why this option was chosen"
            }"""
        )

        self.dropdown_agent = Agent(
            api_key=api_key,
            role="dropdown_selector",
            system_prompt="""You are a form field analyzer specializing in dropdown menu selection.
            Given a list of dropdown options, select the most appropriate one based on these guidelines:
            1. Prefer options that indicate business or service-related choices
            2. Avoid options that are too generic or "other"
            3. Choose options that suggest legitimate interest
            Respond in JSON format:
            {
                "selected_option": "the chosen option",
                "confidence": number between 0-100,
                "reasoning": "why this option was chosen"
            }"""
        )

    async def analyze_form_submission(self, page_content: str) -> Dict[str, Any]:
        return await self.sentiment_agent.analyze(page_content)

    async def select_radio_option(self, options: List[str]) -> Dict[str, Any]:
        return await self.radio_agent.analyze(
            json.dumps(options),
            {"field_type": "radio"}
        )

    async def select_dropdown_option(self, options: List[str]) -> Dict[str, Any]:
        return await self.dropdown_agent.analyze(
            json.dumps(options),
            {"field_type": "dropdown"}
        )

class SentimentAnalyzer:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.agent =Agent(api_key,role="binary Selector",system_prompt="respond either by 'SUCESS' or 'FAILURE' by deciding if the text is error or acceptance message")
        openai.api_key = api_key

    async def analyze_text(self, text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Analyze the given text using the agent.
        """
        try:
            result = await self.agent.analyze(content=text, additional_context=context)
            print(f"[✓] Message analysis result: {result}")
            return result
        except Exception as e:
            print(f"[!] Error analyzing message: {e}")
            return {
                "status": "unknown",
                "confidence": 0,
                "message": str(e),
                "reasoning": "Agent analysis failed"
            }
class FormFieldMapper:
    def __init__(self):
        self.field_patterns = {
            'name': {
                'patterns': ['name', 'first[- ]?name', 'firstname', 'fname', 'full[- ]?name'],
                'value': 'dawood'
            },
            'last_name': {
                'patterns': ['last[- ]?name', 'lastname', 'lname', 'surname', 'family[- ]?name'],
                'value': 'test'
            },
            'email': {
                'patterns': ['email', 'e-mail', 'mail', 'email[- ]?address'],
                'value': 'juneyd.naseer@gmail.com'
            },
            'phone': {
                'patterns': ['phone', 'telephone', 'tel', 'mobile', 'cell', 'contact[- ]?number'],
                'value': '1234567890'
            },
            'message': {
                'patterns': ['message', 'msg', 'comment', 'description', 'details', 'inquiry'],
                'value': 'hi, looking to get a quotation'
            },
            'company': {
                'patterns': ['company', 'business', 'organization', 'org', 'firm'],
                'value': 'Test Company'
            },
            'subject': {
                'patterns': ['subject', 'topic', 'reason', 'purpose'],
                'value': 'Test Subject'
            }
        }
        
        self.form_button_patterns = [
            'get.*quote',
            'request.*quote',
            'contact.*us',
            'get.*started',
            'request.*info',
            'get.*estimate',
            'request.*estimate',
            'get.*pricing',
            'request.*pricing',
            'get.*consultation',
            'request.*consultation',
            'get.*in.*touch',
            'contact.*form',
            'quote.*form',
            'estimate.*form',
            'pricing.*form',
            'consultation.*form'
        ]

    def map_field(self, field_name: str, field_id: str, placeholder: str) -> tuple:
        """Map a field to its appropriate value based on name, id, or placeholder."""
        import re
        
        # Combine all identifiers for matching
        identifiers = [field_name, field_id, placeholder]
        identifiers = [i.lower() for i in identifiers if i]
        
        for field_type, field_info in self.field_patterns.items():
            for pattern in field_info['patterns']:
                for identifier in identifiers:
                    if re.search(pattern, identifier, re.IGNORECASE):
                        return field_type, field_info['value']
        
        return None, None

    def find_button_pattern(self, text: str) -> bool:
        """Check if the text matches any form button patterns."""
        import re
        text = text.lower()
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in self.form_button_patterns)

class DynamicWeb:
    def __init__(self,cap_api,api_key):
        self.sitekey = None
        self.data = None
        self.web = None
        self.Cap_API = cap_api
        self.form_analyzer = FormAnalyzer(api_key)
        self.field_mapper = FormFieldMapper()
        self.sentiment_analyzer = SentimentAnalyzer(api_key)

    def ingestion(self, file):
        try:
            self.data = pd.read_excel(file)
            self.data = self.data['Website'].to_list()
            return self.data
        except Exception as e:
            print("Not Correct file type", e)
            return None

    def Captcha_solver(self,site_key,web):
        self.web=web
        self.sitekey=site_key
        res=requests.post("https://api.capsolver.com/createTask",
                        data={
            "clientKey": self.Cap_API,
            "task": {
                "type": "ReCaptchaV2Task",
                "websiteURL": self.web,
                "websiteKey": self.sitekey
            }
        }).json()
        if res.get("error_id") > 0:
            print(f"Error creating task: {res.get('errorDescription')}")
            return None
        
        task_id = res.get("task_id")

        while True:
            get_captcha = requests.post(
                "https://api.capsolver.com/getTaskResult",
            json={
                "clientKey": self.Cap_API,
                "taskId": task_id
            }
            ).json()

            if get_captcha.get("status") == "ready":
                return get_captcha.get("solution",{}).get("gRecaptchaResponse")

            time.sleep(3)

    async def site_key(self,web):
        self.web=web
        async with async_playwright().start() as p:
            browser= await p.chromium.launch()
            page= await browser.new_page()
            await page.goto(self.web)
            self.sitekey = await page.get_attribute(".g-recaptcha", "data-sitekey")
        return self.sitekey

    async def handle_dropdown_selection(self, page, element) -> bool:
        """Handle dropdown selection using the agent system."""
        try:
            print("[🔍] Processing dropdown selection...")
            
            # Get all options from the dropdown
            options = await element.evaluate("""
                (select) => {
                    return Array.from(select.options).map(option => ({
                        text: option.text,
                        value: option.value,
                        selected: option.selected
                    }));
                }
            """)
            
            if not options:
                print("[!] No options found in dropdown")
                return False
                
            print(f"[✓] Found {len(options)} options in dropdown")
            
            # Extract option texts for the agent
            option_texts = [opt['text'] for opt in options]
            
            # Use the dropdown agent to select the most appropriate option
            selection = await self.form_analyzer.select_dropdown_option(option_texts)
            
            if not selection or 'selected_option' not in selection:
                print("[!] Agent could not make a selection")
                return False
                
            selected_text = selection['selected_option']
            print(f"[✓] Agent selected option: {selected_text}")
            
            # Find the matching option and select it
            for option in options:
                if option['text'] == selected_text:
                    # Select the option
                    await element.select_option(value=option['value'])
                    print(f"[✓] Selected option: {selected_text}")
                    return True
                    
            print("[!] Could not find matching option")
            return False
            
        except Exception as e:
            print(f"[!] Error handling dropdown selection: {str(e)}")
            return False

    async def fill_form(self, page,form_found):
        """Fill the form with appropriate values and return the parent div."""
        try:
            key , value = form_found
            if key == 'id':
                # Get all form fields
                fields = page.locator(f'form#{value}')
                
            else: 
                fields = page.locator(f'form.{value.strip().split()[0]}')
                
            if not fields:
                print("[!] No form fields found")
                return False, None
            # Get all form elements
            form_elements = await fields.locator('''
                input:not([type="submit"]):not([type="hidden"]),
                select,
                textarea
            ''').all()
            
            
            if not form_elements:
                print("[!] No form fields found")
                return False
                
            print(f"[✓] Found {len(form_elements),form_elements} form fields")
            
            for element in form_elements:
                
                # Get element type
                element_type = await element.evaluate('el => el.tagName.toLowerCase()')
                
                if element_type == 'select':
                    # Handle dropdown selection
                    await self.handle_dropdown_selection(page, element)
                    continue
                    
                # Get field attributes
                field_name = await element.get_attribute('name')
                field_id = await element.get_attribute('id')
                placeholder = await element.get_attribute('placeholder')
                
                # Map the field to a value
                field_type, value = self.field_mapper.map_field(field_name, field_id, placeholder)
                # print(field_type, value)
                if field_type and value:
                    # Fill the field
                    await element.fill(value)
                    print(f"[✓] Filled {field_type} field with value: {value}")
                    
                    # Handle special cases
                    if field_type == 'message' and element_type == 'textarea':
                        await element.fill(value)
                        print(f"[✓] Filled textarea with message: {value}")
                    
            # print(f"[*] Found {len(fields)} form fields")
            all_fields_filled = True

            
            

                #     # Check if field is related to CAPTCHA
                #     captcha_indicators = ['captcha', 'recaptcha', 'hcaptcha', 'turnstile', 'verify', 'verification']
                #     field_text = ' '.join([
                #         str(field_context['name'] or ''),
                #         str(field_context['id'] or ''),
                #         str(field_context['placeholder'] or ''),
                #         str(field_context['ariaLabel'] or ''),
                #         str(field_context['parentText'] or ''),
                #         str(field_context['labelText'] or '')
                #     ]).lower()

                #     if any(indicator in field_text for indicator in captcha_indicators):
                #         print(f"[*] Skipping CAPTCHA-related field: {field_text}")
                #         continue

                # except Exception as e:
                #     print(f"[!] Error filling field: {str(e)}")
                #     all_fields_filled = False

            return all_fields_filled

        except Exception as e:
            print(f"[!] Error in fill_form: {str(e)}")
            return False

    async def check_for_captcha(self, page) -> bool:
        """Check if there's a solvable CAPTCHA on the page."""
        try:
            # Check for solvable CAPTCHA elements
            captcha_selectors = [
                'iframe[title="reCAPTCHA"]',
                'iframe[src*="recaptcha/api2/anchor"]',
                'iframe[src*="recaptcha/api2/bframe"]',
                'iframe[src*="recaptcha/enterprise/anchor"]',
                'iframe[src*="recaptcha/enterprise/bframe"]',
                '.g-recaptcha iframe',
                'iframe[src*="challenges.cloudflare.com"]',
                'iframe[src*="hcaptcha"]',
                '.h-captcha',
                '[data-sitekey][data-callback]'
            ]
            
            for selector in captcha_selectors:
                elements = page.locator(selector)
                elements = await elements.all()
                if elements:
                    # Verify it's an actual CAPTCHA by checking for interactive elements
                    for element in elements:
                        try:
                            # Check if the iframe is visible
                            if not await element.is_visible():
                                continue
                                
                            frame = await element.content_frame()
                            if frame:
                                # Check for interactive CAPTCHA elements
                                has_checkbox = (
                                    await frame.locator('div.recaptcha-checkbox, .checkbox-container, .cf-turnstile').count() > 0
                                )
                                has_challenge = (
                                    await frame.locator('div.recaptcha-challenge, .challenge-container, .cf-turnstile-challenge').count() > 0
                                )
                                has_audio = await frame.locator('button.rc-button-audio').count() > 0
                                has_image = await frame.locator('div.rc-imageselect-challenge').count() > 0
                                
                                if any([has_checkbox, has_challenge, has_audio, has_image]):
                                    print(f"[!] Found solvable CAPTCHA: {selector}")
                                    return True
                        except Exception:
                            continue
            
            print("[✓] No solvable CAPTCHA found")
            return False
            
        except Exception as e:
            print(f"[!] Error checking for CAPTCHA: {str(e)}")
            return False

    async def find_button(self, page) -> bool:
        """Find and click a button that might lead to a form."""
        try:
            print("[🔍] Looking for form-related buttons...")
            pattern = re.compile(
                r"Pay Now|get a free Estimate Now|Register|Request a free estimation|"
                r"Request a free quote|Contact\s*us|Get Quotation|Call",
                re.IGNORECASE
            )

            btns = page.get_by_role("button", name=pattern).filter(visible=True)

            count = await btns.count()
            if count:

                btn = btns.first
                await btn.wait_for(state="visible", timeout=5000)
                await btn.click()
                print("✅ Button clicked:", await btn.inner_text())
                return True  
        

            elements = await page.query_selector_all(
                'button, a, [role="button"], input[type="button"], input[type="submit"]'
                    )
            
            for element in elements:
                try:
                    # Get element text
                    text = await element.text_content()
                    if not text:
                        continue

            
                
                    # # Check if text matches form button patterns
                    # if self.submit_form(text,page):
                    #     print(f"[✓] Found potential form button: {text}")
                    
                    if await element.is_visible() and await element.is_enabled():
                        # Scroll the button into view
                        await element.scroll_into_view_if_needed()
                        # Click the button
                        await element.click()
                        print(f"[✓] Clicked button: {text}")
                        return True
                            
                            
                except Exception as e:
                    print(f"[!] Error checking element: {str(e)}")
                    continue
            
            print("[!] No form-related buttons found")
            return False
            
        except Exception as e:
            print(f"[!] Error finding form button: {str(e)}")
            return False

    async def find_form_elements(self, page) -> bool:
        """Find form elements on the page using multiple detection strategies."""
        try:
            print("[🔍] Searching for form relevant button...")
            form_btn = page.locator("button").filter(has_text=re.compile(
                    r"Submit | Send Message | Pay Now|get a free Estimate Now|Register|Request a free estimation|"
                    r"Request a free quote|Contact\s*us|Get Quotation|Call",
                    re.IGNORECASE))
            buttons = await form_btn.all()
            ##first here it will check for form elemetns using buttons , if none found , will move to next strategy
            if buttons:
                for btn in buttons:
                    
                    # # start_url = page.url
                    # try:
                    #     # await btn.click()
                    #     await page.wait_for_load_state('networkidle')
                    # except Exception as e:
                    #     print("Error on click:", e)
                    try:
                        form = btn.locator("xpath=ancestor::form")
                        if not await form.count() > 0:
                            print("❌ No form ancestor for this button. Going back...")
                            await page.go_back()
                            await page.wait_for_load_state('networkidle')
                            continue
                        else:
                            form_id = await form.get_attribute('id')
                            form_class = await form.get_attribute('class')
                            identifier = ('id', form_id) if form_id else ('class', form_class)
                            return identifier
                            
                    except Exception as e:
                        print(str(e))
            

            # # Strategy 1: Check for actual form structure
            try:
                # First check for traditional form tags
                form_elements = await page.query_selector_all('form')
                if form_elements:
                    # Verify these are actual forms with input fields
                    for form in form_elements:
                        if await form.is_visible():
                            inputs = await form.query_selector_all('''
                            input:not([type="hidden"]),
                            select,
                            textarea
                        ''')
                        valid_inputs = []
                        for inp in inputs:
                            # Ignore honeypot fields like name="website"
                            name = await inp.get_attribute("name")
                            if name and "website" in name.lower():
                                continue

                            style = await inp.evaluate('el => window.getComputedStyle(el)')
                            if style['display'] != 'none' and style['visibility'] != 'hidden' and style['opacity'] != '0':
                                valid_inputs.append(inp)

                        if valid_inputs and len(valid_inputs) >= 3:
                            print("[✓] Found valid form with input fields (adjusted strategy)")
                            form_id = await form.get_attribute('id')
                            form_class = await form.get_attribute('class')
                            identifier = ('id', form_id) if form_id else ('class', form_class)
                            return identifier
            except Exception:
                pass

            # Strategy 2: Check for form-like structures using Readability.js approach
            try:
                # Get all potential form containers
                form_containers = await page.evaluate("""
                    () => {
                        // Function to check if element is visible
                        const isVisible = (el) => {
                            const style = window.getComputedStyle(el);
                            return style.display !== 'none' && 
                                   style.visibility !== 'hidden' && 
                                   style.opacity !== '0' &&
                                   el.offsetParent !== null;
                        };

                        // Function to check if element is likely a form
                        const isLikelyForm = (el) => {
                            // Must have input fields
                            const inputs = el.querySelectorAll('input:not([type="submit"]):not([type="hidden"]), select, textarea');
                            if (inputs.length === 0) return false;

                            // Must have submit button or similar
                            const hasSubmit = el.querySelector('button[type="submit"], input[type="submit"], button:not([type]), [role="button"], .form-submit-button');
                            if (!hasSubmit) return false;

                            // Check for form-like attributes
                            const hasFormAttr = el.hasAttribute('role') && el.getAttribute('role') === 'form' ||
                                              el.hasAttribute('data-form') ||
                                              el.hasAttribute('data-wf-form') ||
                                              el.hasAttribute('data-form-type');

                            // Check for form-like classes
                            const hasFormClass = el.className.includes('form') ||
                                                el.className.includes('jotform') ||
                                                el.className.includes('jf-required') ||
                                                el.className.includes('page-section') ||
                                                el.className.includes('form-line') ||
                                                el.className.includes('gform');

                            // Check for form-like structure
                            const hasFormStructure = el.querySelector('label') !== null ||
                                                   el.querySelector('fieldset') !== null ||
                                                   el.querySelector('legend') !== null;

                            return (hasFormAttr || hasFormClass || hasFormStructure) && isVisible(el);
                        };

                        // Get all potential form containers
                        const containers = Array.from(document.querySelectorAll('div, section, article, ul, form'));

                        return containers.filter(isLikelyForm).map(el => ({
                            tagName: el.tagName,
                            className: el.className,
                            id: el.id,
                            hasInputs: el.querySelectorAll('input, select, textarea').length,
                            hasSubmit: !!el.querySelector('button[type="submit"], input[type="submit"]'),
                            isVisible: isVisible(el)
                        }));
                    }
                """)

                if form_containers and len(form_containers) > 0:
                    # Log the found containers for debugging
                    print(f"[ℹ️] Found {len(form_containers)} potential form containers")
                    for container in form_containers:
                        print(f"[ℹ️] Container: {container['tagName']} (class: {container['className']}, id: {container['id']})")
                        print(f"[ℹ️] Has {container['hasInputs']} inputs, submit: {container['hasSubmit']}, visible: {container['isVisible']}")
                    
                    # Verify at least one container is a valid form
                    valid_containers = [c for c in form_containers if c['hasInputs'] > 0 and c['hasSubmit'] and c['isVisible']]
                    if valid_containers:
                        print("[✓] Found valid form-like structure")
                        form_id = await form.get_attribute('id')
                        form_class = await form.get_attribute('class')
                        identifier = ('id', form_id) if form_id else ('class', form_class)
                        return identifier

            except Exception as e:
                print(f"[!] Error in form-like structure detection: {str(e)}")


        except Exception as e:
            print(f"[!] Error finding form elements: {str(e)}")
            return False

    async def process_page(self, page, url: str) -> bool:
        """Process a single page for form filling."""
        try:
            print(f"\n[🌐] Processing URL: {url}")
            # import pdb;pdb.set_trace()
            # Navigate to the page
            await page.goto(url, wait_until="networkidle")
            print("[✓] Page loaded successfully")
            
            # # return True if solvable captcha found , otherwise false
            # captcha_present = await self.check_for_captcha(page)
            # if not captcha_present:
            #     print("[!]No solvable Captcha Found")
                
            
            # First try to find and fill form on current page
            form_found = await self.find_form_elements(page)
            if form_found is not None:
                print(f"[✓] Form found with ID:{form_found} on current page")
                # Fill the form
                success = await self.fill_form(page,form_found)
                if not success:
                    print("[!] Failed to fill form")
                    return False
            else:
                print("[!] No form found on current page, looking for form button...")
                # Try to find and click a button that might lead to a form
                success = await self.find_button(page)
                await page.wait_for_load_state("networkidle")
                if not success:
                    print("[!] Could not find button that lead to form")
                    return False
                
                form_found = await self.find_form_elements(page)
                try:
                    if form_found:
                        # Fill the form on the new page
                        success = await self.fill_form(page,form_found)
                        
                        if not success:
                            print("[!] Failed to fill form")
                            return False
                    
                except Exception as e:
                    print(f"none found{str(e)}")
            
            # Submit the form
            success = await self.submit_form('input[type="submit"]',url, page, form_found)
            if not success:
                print("[!] Form submission failed or could not be verified")
                return False
            
            print("[✓] Form processed successfully")
            return True
            
        except Exception as e:
            print(f"[!] Error processing URL {url}: {str(e)}")
            return False

    async def submit_form(self, selector: str,url, page, identifier, parent_div=None) -> bool:
        """Submit the form and verify the submission.
            Will  add parent div button check case later on"""
        try:
            print("[🔍] Monitoring Form Submission")
            
            # Get the initial URL
            initial_url = page.url
            key , value = identifier
            
            # Try multiple selectors for submit buttons
            submit_selectors = [
                'input[type="submit"]',
                'button[type="submit"]',
                'button:not([type])',  # Buttons without type default to submit
                '[role="button"]',
                'button.submit',
                'button[class*="submit"]',
                'button[class*="send"]',
                'button[class*="form"]',
                'input[class*="submit"]',
                'input[class*="send"]',
                'input[class*="form"]',
                'button:has-text("Submit")',
                'button:has-text("Send")',
                'button:has-text("Get Quote")',
                'button:has-text("Request Quote")',
                'button:has-text("Contact Us")',
                'button:has-text("Send Message")',
                'button:has-text("Submit Form")'
            ]
            
            submit_button = None
            for sel in submit_selectors:
                try:
                    if key == 'id':
                        # Get all form fields
                        button = page.locator(f'form#{value}')
                        
                    else: 
                        button = page.locator(f'form.{value.strip().split()[0]}')
                   

                    if await button.count() > 0:
                        # Check if any instance of this button is visible
                        is_visible = await button.evaluate_all("""
                            (buttons) => buttons.some(button => {
                                const style = window.getComputedStyle(button);
                                return style.display !== 'none' && 
                                    style.visibility !== 'hidden' && 
                                    style.opacity !== '0' &&
                                    button.offsetParent !== null;
                            })
                        """)
                        
                        if is_visible:
                            submit_button = button
                            print(f"[✓] Found visible submit button with selector: {sel}")
                            break
                except Exception:
                    continue
            
            if not submit_button:
                print("[!] No visible submit button found in the form div")
                return False

            # Get the form method and check if it's using JavaScript
            form_info = await page.evaluate("""
                (selector) => {
                    const button = document.querySelector(selector);
                    if (!button) return { method: 'get', hasSubmitHandler: false };
                    
                    const form = button.closest('form');
                    if (!form) return { method: 'get', hasSubmitHandler: false };
                    
                    const hasSubmitHandler = form.onsubmit !== null || 
                        form.getAttribute('onsubmit') !== null ||
                        form.hasAttribute('data-wf-form');
                        
                    return {
                        method: form.method.toLowerCase(),
                        hasSubmitHandler: hasSubmitHandler
                    };
                }
            """, selector)
            # form_info = await page.evaluate("""
            #     (formSelector) => {
            #         const form = document.querySelector(formSelector);
            #         if (!form) return { method: 'get', hasSubmitHandler: false };

            #         const hasSubmitHandler =
            #             form.onsubmit !== null ||
            #             form.getAttribute('onsubmit') !== null ||
            #             form.hasAttribute('data-wf-form');

            #         return {
            #             method: form.method ? form.method.toLowerCase() : 'get',
            #             hasSubmitHandler
            #         };
            #     }
            # """, selector)
            
            print(f"[📡] Form method: {form_info['method']}")
            print(f"[📡] Has submit handler: {form_info['hasSubmitHandler']}")

            async def check_success_indicators(response_status=None):
                """Check various success indicators and return probability of successful submission"""
                indicators = {
                    'response_status': 0,
                    'url_change': 0,
                    'message': 0
                }

                if response_status is not None:
                    indicators['response_status'] = 1 if response_status in [200, 201, 202, 204, 302] else 0
                    print(f"[✓] Response status: {response_status}")

                current_url = page.url
                if current_url != initial_url:
                    indicators['url_change'] = (
                        1 if any(w in current_url.lower() for w in ['thank', 'success']) else 0.5
                    )
                    print("[✓] URL changed or contains success indicators")

                # === Look for success/failure messages ===
                form_selector = (
                    f'form#{value}' if key == 'id'
                    else f'form.{value.strip().split()[0]}' if key == 'class'
                    else parent_div
                )

                try:
                    if form_selector:
                        content = await page.locator(form_selector).inner_text()
                    else:
                        content = await page.content()
                    
                    analysis = await self.sentiment_analyzer.analyze_text(content)
                    if analysis['status'] == 'success':
                        indicators['message'] = 1
                    elif analysis['status'] == 'error':
                        indicators['message'] = 0
                    else:
                        indicators['message'] = 0.5

                    print(f"[✓] Agent message analysis: {analysis['status']} — {analysis['reasoning']}")
                except Exception as e:
                    print(f"[!] Failed to analyze message: {e}")

                final_prob = (
                    indicators['response_status'] * 0.5 +
                    indicators['url_change'] * 0.3 +
                    indicators['message'] * 0.2
                )
                print(f"[📊] Final submission probability: {final_prob:.2f}")
                return final_prob >= 0.5


            ##If there is a solvable captcha , solve it
            # First check for "protected by CAPTCHA" messages
            captcha_message_selectors = [
                'text="protected by CAPTCHA"',
                'text="protected by reCAPTCHA"',
                'text="protected by captcha"',
                '[class*="captcha-protected"]',
                '[id*="captcha-protected"]'
            ]

            for selector in captcha_message_selectors:
                try:
                    if await page.locator(selector).count() > 0:
                        print(f"[!] Site is protected by CAPTCHA: {selector}")
                        return {"status": "error", "message": "Site is protected by CAPTCHA and cannot be automated"}
                except Exception:
                    continue

            # CAPTCHA detection
            captcha_selectors = [
                'iframe[title="reCAPTCHA"]',
                'iframe[src*="recaptcha"]',
                '.g-recaptcha',
                'iframe[title*="recaptcha"]'
            ]

            for selector in captcha_selectors:
                try:
                    if await page.locator(selector).count() > 0:
                        print(f"[🤖] reCAPTCHA detected: {selector}")
                        
                        # Get site key using the existing method
                        site_key = await self.site_key(url)
                        if not site_key:
                            print("[!] Could not find site key")
                            continue

                        print(f"[🔑] Found site key: {site_key}")
                        
                        # Solve CAPTCHA
                        solver = self.Captcha_solver(site_key, url)
                        if not solver:
                            print("[!] Failed to solve CAPTCHA")
                            continue

                        # Set the response
                        await page.evaluate(f'''
                            document.querySelector("textarea[name='g-recaptcha-response']").style.display = 'block';
                            document.querySelector("textarea[name='g-recaptcha-response']").value = "{solver}";
                        ''')
                        print("[✓] CAPTCHA response set")
                        break

                except Exception as e:
                    print(f"[!] Error handling reCAPTCHA: {str(e)}")
                    continue

            # === Submit the form ===
            expecter = page.expect_response(lambda response: (
                response.request.method in ['POST', 'PUT'] and
                'form' in response.request.headers.get('content-type', '').lower()
            )) if form_info['method'] != 'get' and not form_info['hasSubmitHandler'] else \
                page.expect_response(lambda response: 'analytics' not in response.url.lower())

            async with expecter as response_info:
                try:
                    try:
                        await submit_button.click(force=True, timeout=5000)
                    except Exception:
                        try:
                            await submit_button.evaluate('b => b.click()')
                        except Exception:
                            await submit_button.evaluate('b => b.dispatchEvent(new MouseEvent("click", {bubbles: true}))')

                    try:
                        response = await response_info.value
                        print(f"[📡] Request URL: {response.url}")
                        print(f"[📡] Response Status: {response.status}")
                        await page.wait_for_load_state("networkidle")
                        return await check_success_indicators(response.status)
                    except Exception:
                        await page.wait_for_load_state("networkidle")
                        return await check_success_indicators()
                except Exception as e:
                    print(f"[!] Error during form submission: {e}")
                    return False

        except Exception as e:
            print(f"[!] Unexpected error in submit_form: {e}")
            return False
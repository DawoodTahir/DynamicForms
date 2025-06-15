import pandas as pd
from io import BytesIO
import requests
from playwright.async_api import async_playwright
import time
import re
import openai
from typing import Optional, Dict, Any, List
import json

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
        openai.api_key = api_key
        self.success_patterns = [
            r'thank you',
            r'thanks',
            r'success',
            r'successfully',
            r'received',
            r'submitted',
            r'we\'ll contact you',
            r'we will contact you',
            r'confirmation',
            r'your message has been sent',
            r'form submitted',
            r'we\'ve received',
            r'we have received'
        ]
        
        self.error_patterns = [
            r'error',
            r'failed',
            r'invalid',
            r'incorrect',
            r'required',
            r'missing',
            r'please try again',
            r'could not submit',
            r'failed to submit',
            r'please check',
            r'please enter',
            r'please provide'
        ]

    async def analyze_response(self, page_content: str) -> Dict[str, Any]:
        """
        Analyze the page content after form submission to determine if it's a success or error message.
        Returns a dictionary with analysis results.
        """
        try:
            # Prepare the prompt for ChatGPT
            prompt = f"""
            Analyze this webpage content after a form submission and determine:
            1. Is this a success message, error message, or neither?
            2. What is the confidence level (0-100)?
            3. What is the main message?

            Content:
            {page_content}

            Respond in JSON format:
            {{
                "status": "success" or "error" or "unknown",
                "confidence": number between 0-100,
                "message": "main message found",
                "reasoning": "brief explanation"
            }}
            """

            # Call ChatGPT API
            response = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a form submission response analyzer. Analyze the content and determine if it's a success or error message."},
                    {"role": "user", "content": prompt}
                ]
            )

            # Extract and parse the response
            analysis = response.choices[0].message.content
            return eval(analysis)  # Convert string JSON to dict

        except Exception as e:
            print(f"[!] Error in sentiment analysis: {str(e)}")
            return {
                "status": "unknown",
                "confidence": 0,
                "message": "Error in analysis",
                "reasoning": str(e)
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

    def find_form_button(self, text: str) -> bool:
        """Check if the text matches any form button patterns."""
        import re
        text = text.lower()
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in self.form_button_patterns)

class DynamicWeb:
    def __init__(self):
        self.sitekey = None
        self.data = None
        self.web = None
        self.Cap_API = "CAP-C923AE479F371BD716FEB2D7874F9923874EA93B7FB0F2D389FD4321E2405246"
        self.form_analyzer = FormAnalyzer("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")
        self.field_mapper = FormFieldMapper()

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

    async def fill_form(self, page) -> bool:
        """Fill form fields using the field mapper."""
        try:
            print("[📝] Filling form fields...")
            
            # Get all form elements
            form_elements = await page.query_selector_all('''
                input:not([type="submit"]):not([type="hidden"]),
                select,
                textarea
            ''')
            
            if not form_elements:
                print("[!] No form fields found")
                return False
                
            print(f"[✓] Found {len(form_elements)} form fields")
            
            for element in form_elements:
                try:
                    # Get element type
                    element_type = await element.evaluate('el => el.tagName.toLowerCase()')
                    field_name = await element.get_attribute('name')
                    field_id = await element.get_attribute('id')
                    placeholder = await element.get_attribute('placeholder')
                    field_type = await element.get_attribute('type')
                    
                    # Map the field to a value
                    field_type, value = self.field_mapper.map_field(field_name, field_id, placeholder)
                    
                    if field_type and value:
                        # Fill the field
                        await element.fill(value)
                        print(f"[✓] Filled {field_type} field with mapped value: {value}")
                        continue
                    
                    # If field mapper didn't find a match, use agent system
                    print(f"[🤖] Using agent to analyze field: {field_name or field_id or placeholder}")
                    
                    # Get field context for agent
                    field_context = await element.evaluate("""
                        (el) => {
                            const context = {
                                type: el.type,
                                name: el.name,
                                id: el.id,
                                placeholder: el.placeholder,
                                label: el.labels ? Array.from(el.labels).map(l => l.textContent).join(' ') : '',
                                ariaLabel: el.getAttribute('aria-label'),
                                role: el.getAttribute('role'),
                                class: el.className,
                                parentText: el.parentElement ? el.parentElement.textContent : '',
                                siblingText: Array.from(el.parentElement?.children || [])
                                    .filter(child => child !== el)
                                    .map(child => child.textContent)
                                    .join(' ')
                            };
                            return context;
                        }
                    """)
                    
                    # Use agent to analyze field and get appropriate value
                    field_analysis = await self.form_analyzer.analyze_form_field(field_context)
                    
                    if field_analysis and 'value' in field_analysis:
                        # Fill the field with agent's suggested value
                        await element.fill(field_analysis['value'])
                        print(f"[✓] Filled field with agent-suggested value: {field_analysis['value']}")
                        print(f"[📝] Agent reasoning: {field_analysis.get('reasoning', 'No reasoning provided')}")
                    else:
                        print(f"[!] Agent could not determine value for field: {field_name or field_id or placeholder}")
                    
                    # Handle special cases
                    if element_type == 'select':
                        await self.handle_dropdown_selection(page, element)
                    elif element_type == 'textarea':
                        # For textareas, ensure we have a proper message
                        if not value:
                            value = "I am interested in your services and would like to know more. Please contact me at your earliest convenience."
                        await element.fill(value)
                        print(f"[✓] Filled textarea with message: {value}")
                    
                except Exception as e:
                    print(f"[!] Error filling field {field_name or field_id}: {str(e)}")
                    continue
            
            print("[✓] Form fields filled successfully")
            return True
            
        except Exception as e:
            print(f"[!] Error in fill_form: {str(e)}")
            return False

    async def check_for_captcha(self, page) -> bool:
        """Check if there's a CAPTCHA on the page."""
        try:
            captcha_selectors = [
                'iframe[title="reCAPTCHA"]',
                'iframe[src*="recaptcha"]',
                '.g-recaptcha',
                'iframe[title*="recaptcha"]'
            ]
            
            for selector in captcha_selectors:
                if await page.locator(selector).count() > 0:
                    print(f"[!] Found CAPTCHA with selector: {selector}")
                    return True
                    
            print("[✓] No CAPTCHA found on page")
            return False
            
        except Exception as e:
            print(f"[!] Error checking for CAPTCHA: {str(e)}")
            return False

    async def find_and_click_form_button(self, page) -> bool:
        """Find and click a button that might lead to a form."""
        try:
            print("[🔍] Looking for form-related buttons...")
            
            # Get all buttons and links
            elements = await page.query_selector_all('''
                button,
                a,
                [role="button"],
                input[type="button"],
                input[type="submit"]
            ''')
            
            for element in elements:
                try:
                    # Get element text
                    text = await element.text_content()
                    if not text:
                        continue
                        
                    # Check if text matches form button patterns
                    if self.field_mapper.find_form_button(text):
                        print(f"[✓] Found potential form button: {text}")
                        
                        # Check if element is visible and clickable
                        if await element.is_visible() and await element.is_enabled():
                            # Click the button
                            await element.click()
                            print(f"[✓] Clicked button: {text}")
                            
                            # Wait for navigation or form to appear
                            await page.wait_for_load_state("networkidle")
                            
                            # Check if we're on a form page
                            form_elements = await page.query_selector_all('form')
                            if form_elements:
                                print("[✓] Form found after clicking button")
                                return True
                            else:
                                print("[!] No form found after clicking button")
                                return False
                                
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
            print("[🔍] Searching for form elements...")
            
            # Strategy 1: Quick check for traditional form elements
            try:
                form_elements = await page.query_selector_all('form')
                if form_elements:
                    print("[✓] Found traditional form elements")
                    return True
            except Exception:
                pass

            # Strategy 2: Common form container patterns with timeout
            try:
                # Use Promise.race to add timeout to query_selector_all
                has_form = await page.evaluate("""
                    async () => {
                        const timeout = new Promise((_, reject) => 
                            setTimeout(() => reject('timeout'), 3000)
                        );
                        
                        const checkForm = async () => {
                            const selectors = [
                                'div[data-wp-interactive*="form"]',
                                'div[data-wp-interactive*="contact"]',
                                'div[class*="form"]',
                                'div[class*="contact"]',
                                'div[class*="wpcf7"]',
                                'div[class*="gform"]',
                                'div[role="form"]',
                                'div[data-form]'
                            ];
                            
                            for (const selector of selectors) {
                                const elements = document.querySelectorAll(selector);
                                for (const el of elements) {
                                    // Skip lightboxes
                                    if (el.classList.contains('wp-lightbox-overlay') ||
                                        el.classList.contains('lightbox') ||
                                        el.getAttribute('data-wp-interactive')?.includes('image')) {
                                        continue;
                                    }
                                    
                                    // Check for form elements
                                    const inputs = el.querySelectorAll('input:not([type="submit"]):not([type="hidden"]), select, textarea');
                                    const buttons = el.querySelectorAll('button, [type="submit"], [role="button"]');
                                    
                                    if (inputs.length > 0 && buttons.length > 0) {
                                        return true;
                                    }
                                }
                            }
                            return false;
                        };
                        
                        return await Promise.race([checkForm(), timeout]);
                    }
                """)
                
                if has_form:
                    print("[✓] Found form container")
                    return True
            except Exception as e:
                if str(e) != 'timeout':
                    print(f"[!] Error in form container check: {str(e)}")

            # Strategy 3: Quick check for iframe forms
            try:
                iframes = await page.query_selector_all('iframe')
                for iframe in iframes:
                    try:
                        frame = await iframe.content_frame()
                        if frame:
                            form_elements = await frame.query_selector_all('form')
                            if form_elements:
                                print("[✓] Found form in iframe")
                                return True
                    except Exception:
                        continue
            except Exception:
                pass

            # Strategy 4: Final check for dynamic forms with short timeout
            try:
                await page.wait_for_selector('form', timeout=2000)
                print("[✓] Found dynamically loaded form")
                return True
            except Exception:
                pass

            print("[!] No form elements found")
            return False

        except Exception as e:
            print(f"[!] Error finding form elements: {str(e)}")
            return False

    async def process_page(self, page, url: str) -> bool:
        """Process a single page for form filling."""
        try:
            print(f"\n[🌐] Processing URL: {url}")
            
            # Navigate to the page
            await page.goto(url, wait_until="networkidle")
            print("[✓] Page loaded successfully")
            
            # Check for CAPTCHA
            captcha_present = await self.check_for_captcha(page)
            if captcha_present:
                print("[!] CAPTCHA found on page")
                return False
            
            # First try to find and fill form on current page
            form_found = await self.find_form_elements(page)
            if form_found:
                print("[✓] Form found on current page")
                # Fill the form
                success = await self.fill_form(page)
                if not success:
                    print("[!] Failed to fill form")
                    return False
            else:
                print("[!] No form found on current page, looking for form button...")
                # Try to find and click a button that might lead to a form
                success = await self.find_and_click_form_button(page)
                if not success:
                    print("[!] Could not find or access form")
                    return False
                    
                # Fill the form on the new page
                success = await self.fill_form(page)
                if not success:
                    print("[!] Failed to fill form")
                    return False
            
            # Submit the form
            success = await self.submit_form('input[type="submit"]', page)
            if not success:
                print("[!] Form submission failed or could not be verified")
                return False
            
            print("[✓] Form processed successfully")
            return True
            
        except Exception as e:
            print(f"[!] Error processing URL {url}: {str(e)}")
            return False

    async def submit_form(self, selector: str, page) -> bool:
        """Submit the form and verify the submission."""
        try:
            print("[🔍] Monitoring Form Submission")
            
            # Get the initial URL
            initial_url = page.url
            
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
                    button = page.locator(sel)
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
                print("[!] No visible submit button found, trying to find form and submit it")
                # Try to find the form and submit it directly
                forms = await page.query_selector_all('form')
                if forms:
                    for form in forms:
                        try:
                            # Check if form is visible
                            is_visible = await form.evaluate("""
                                (form) => {
                                    const style = window.getComputedStyle(form);
                                    return style.display !== 'none' && 
                                           style.visibility !== 'hidden' && 
                                           style.opacity !== '0' &&
                                           form.offsetParent !== null;
                                }
                            """)
                            
                            if is_visible:
                                print("[✓] Found visible form, submitting directly")
                                await form.evaluate('form => form.submit()')
                                return True
                        except Exception:
                            continue
                
                print("[!] Could not find any submit button or form to submit")
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
                    if 'thank' in current_url.lower() or 'success' in current_url.lower():
                        indicators['url_change'] = 1
                        print("[✓] URL contains thank you/success")
                    else:
                        indicators['url_change'] = 0.5
                        print("[✓] URL changed")

                message_selectors = [
                    '.form-message-success', '.w-form-done',
                    '[class*="success"]', '[class*="thank"]',
                    '[id*="success"]', '[id*="thank"]',
                    '.form-message-error', '.w-form-fail',
                    '[class*="error"]', '[class*="fail"]',
                    '[id*="error"]', '[id*="fail"]'
                ]

                for selector in message_selectors:
                    try:
                        element = page.locator(selector)
                        if await element.count() > 0 and await element.is_visible():
                            text = await element.text_content()
                            if any(word in text.lower() for word in ['thank', 'success']):
                                indicators['message'] = 1
                                print(f"[✓] Found visible thank you message: {text}")
                                break
                            elif any(word in text.lower() for word in ['error', 'fail']):
                                indicators['message'] = -1
                                print(f"[!] Found visible error message: {text}")
                                break
                    except Exception:
                        continue

                final_probability = (
                    indicators['response_status'] * 0.5 +
                    indicators['url_change'] * 0.3 +
                    (indicators['message'] if indicators['message'] >= 0 else 0) * 0.2
                )

                print(f"[📊] Submission indicators:")
                print(f"  Response Status: {indicators['response_status']}")
                print(f"  URL Change: {indicators['url_change']}")
                print(f"  Message: {indicators['message']}")
                print(f"[📊] Final submission probability: {final_probability:.2f}")

                return final_probability >= 0.5

            if form_info['method'] == 'get' or form_info['hasSubmitHandler']:
                try:
                    async with page.expect_response(lambda response: 
                        not any(analytics in response.url.lower() for analytics in ['google-analytics', 'analytics', 'tracking', 'pixel'])
                    ) as response_info:
                        # Try multiple ways to click the button
                        try:
                            await submit_button.click(force=True, timeout=5000)
                        except Exception:
                            try:
                                await submit_button.evaluate('button => button.click()')
                            except Exception:
                                await submit_button.evaluate('button => button.dispatchEvent(new MouseEvent("click", {bubbles: true}))')
                        
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
                    print(f"[!] Error with form submission: {str(e)}")
                    return False
            else:
                async with page.expect_response(lambda response: 
                    (response.request.method in ['POST', 'PUT'] and
                    not any(analytics in response.url.lower() for analytics in ['google-analytics', 'analytics', 'tracking', 'pixel']) and
                    ('form' in response.request.headers.get('content-type', '').lower() or
                     'application/json' in response.request.headers.get('content-type', '').lower() or
                     'text/plain' in response.request.headers.get('content-type', '').lower()))
                ) as response_info:
                    try:
                        # Try multiple ways to click the button
                        try:
                            await submit_button.click(force=True, timeout=5000)
                        except Exception:
                            try:
                                await submit_button.evaluate('button => button.click()')
                            except Exception:
                                await submit_button.evaluate('button => button.dispatchEvent(new MouseEvent("click", {bubbles: true}))')
                                
                        response = await response_info.value
                        print(f"[📡] Request URL: {response.url}")
                        print(f"[📡] Response Status: {response.status}")
                        await page.wait_for_load_state("networkidle")
                        return await check_success_indicators(response.status)
                            
                    except Exception as e:
                        print(f"[!] Error with POST form submission: {str(e)}")
                        return False
                
        except Exception as e:
            print(f"[!] Error during form submission: {str(e)}")
            return False

    async def run(self, urls: List[str]):
        """Run the form filling process for a list of URLs."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            
            for url in urls:
                try:
                    print(f"\n[🌐] Navigating to {url}")
                    # Navigate to the page first
                    await page.goto(url, wait_until="networkidle")
                    # Then process the page
                    success = await self.process_page(page, url)
                    if not success:
                        print(f"[!] Failed to process {url}")
                        continue
                        
                except Exception as e:
                    print(f"[!] Error processing {url}: {str(e)}")
                    continue
                    
            await browser.close()


            
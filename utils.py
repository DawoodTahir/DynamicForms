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
    def __init__(self, user_data=None, default_json_path='app/static/default-values.json'):
        self.user_data = user_data or {}
        self.default_json_path = default_json_path
        self.default_values = None
        self.field_patterns = {
            'name': {
                'patterns': ['name', 'first[- ]?name', 'firstname', 'fname', 'full[- ]?name'],
                'key': 'firstName',
            },
            'last_name': {
                'patterns': ['last[- ]?name', 'lastname', 'lname', 'surname', 'family[- ]?name'],
                'key': 'lastName',
            },
            'email': {
                'patterns': ['email', 'e-mail', 'mail', 'email[- ]?address'],
                'key': 'email',
            },
            'phone': {
                'patterns': ['phone', 'telephone', 'tel', 'mobile', 'cell', 'contact[- ]?number'],
                'key': 'phone',
            },
            'message': {
                'patterns': ['message', 'msg', 'comment', 'description', 'details', 'inquiry'],
                'key': 'message',
            },
            'company': {
                'patterns': ['company', 'business', 'organization', 'org', 'firm'],
                'key': 'company',
            },
            'subject': {
                'patterns': ['subject', 'topic', 'reason', 'purpose'],
                'key': 'subject',
            },
            'address': {
                'patterns': ['address', 'street', 'address1', 'address2'],
                'key': 'address',
            },
            'city': {
                'patterns': ['city', 'town'],
                'key': 'city',
            },
            'state': {
                'patterns': ['state', 'province', 'region'],
                'key': 'state',
            },
            'zip': {
                'patterns': ['zip', 'postal', 'postcode', 'zip[- ]?code'],
                'key': 'zipCode',
            },
            'country': {
                'patterns': ['country'],
                'key': 'country',
            },
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

    def get_default_values(self):
        if self.default_values is not None:
            return self.default_values
        try:
            import json
            with open(self.default_json_path, 'r') as f:
                self.default_values = json.load(f)
        except Exception:
            # fallback values
            self.default_values = {
                'firstName': 'John',
                'lastName': 'Doe',
                'email': 'john.doe@example.com',
                'phone': '+1 (555) 123-4567',
                'address': '123 Main Street',
                'city': 'New York',
                'state': 'NY',
                'zipCode': '10001',
                'country': 'United States',
                'message': 'Hi, I am interested in your services and would like to get a quote. Please contact me with more information.'
            }
        return self.default_values

    def map_field(self, field_name: str, field_id: str, placeholder: str) -> tuple:
        import re
        identifiers = [field_name, field_id, placeholder]
        identifiers = [i.lower() for i in identifiers if i]
        for field_type, field_info in self.field_patterns.items():
            for pattern in field_info['patterns']:
                for identifier in identifiers:
                    if re.search(pattern, identifier, re.IGNORECASE):
                        key = field_info['key']
                        # Use user_data if present, else default values
                        value = self.user_data.get(key)
                        if value is None:
                            value = self.get_default_values().get(key)
                        return field_type, value
        return None, None

    def find_button_pattern(self, text: str) -> bool:
        """Check if the text matches any form button patterns."""
        import re
        text = text.lower()
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in self.form_button_patterns)

class FormNavigationAgent:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.agent = Agent(
            api_key=api_key,
            role="form_navigation_analyzer",
            system_prompt="""You are a form navigation analyzer. Your job is to analyze clickable elements and determine which one is most likely to lead to a form or quote request page.

            Given a list of clickable elements with their text, class names, and IDs, analyze which one is most likely to lead to a form.

            Consider these factors:
            1. Elements that suggest form submission (request, quote, estimate, contact, get, register)
            2. Elements that indicate business services (consultation, pricing, info, start, begin)
            3. Elements that suggest user action (submit, send, pay, call)
            4. Elements with form-related classes (btn, button, cta, submit, send, request, quote, contact, estimate)

            Respond in JSON format:
            {
                "best_element_index": number (index of the best element, -1 if none found),
                "confidence": number between 0-100,
                "reasoning": "why this element was chosen",
                "element_text": "text of the chosen element"
            }"""
        )

    async def analyze_navigation_elements(self, elements: List[Dict]) -> Dict[str, Any]:
        """Analyze clickable elements to find the best navigation option."""
        try:
            if not elements:
                return {
                    "best_element_index": -1,
                    "confidence": 0,
                    "reasoning": "No elements to analyze",
                    "element_text": ""
                }

            # Prepare element data for analysis
            element_data = []
            for i, element in enumerate(elements):
                element_data.append({
                    "index": i,
                    "text": element.get('text', ''),
                    "className": element.get('className', ''),
                    "id": element.get('id', ''),
                    "tagName": element.get('tagName', '')
                })

            # Create analysis prompt
            analysis_prompt = f"""
            Analyze these clickable elements to find the one most likely to lead to a form or quote request:

            {json.dumps(element_data, indent=2)}

            Which element is most likely to lead to a form? Consider:
            - Text content that suggests form submission
            - Class names that indicate form-related functionality
            - IDs that suggest form navigation
            - Overall context and business relevance

            Return the index of the best element (0-based) and explain why you chose it.
            """

            # Use the agent to analyze
            result = await self.agent.analyze(analysis_prompt)
            
            print(f"[🤖] Agent response: {result}")
            
            # Try to extract best_element_index from the result
            best_index = result.get('best_element_index', -1)
            reasoning = result.get('reasoning', '')
            message = result.get('message', '')
            
            # If agent didn't provide a valid index, use fallback logic
            if best_index == -1 or best_index >= len(elements):
                print("[⚠️] Agent didn't provide valid index, using fallback logic...")
                
                # Priority-based selection
                priority_keywords = [
                    'request free estimate', 'request estimate', 'request quote', 'get quote',
                    'request', 'quote', 'estimate', 'contact', 'get', 'submit'
                ]
                
                best_index = 0
                best_score = 0
                
                for i, element in enumerate(elements):
                    element_text = element.get('text', '').lower()
                    element_class = element.get('className', '').lower()
                    
                    # Calculate score based on keywords
                    score = 0
                    for keyword in priority_keywords:
                        if keyword in element_text:
                            score += priority_keywords.index(keyword) + 1  # Higher score for earlier keywords
                    
                    # Bonus for button classes
                    if any(btn_class in element_class for btn_class in ['button', 'btn', 'cta']):
                        score += 5
                    
                    # Penalty for social media and non-form elements
                    if any(social in element_text for social in ['facebook', 'twitter', 'x', 'instagram', 'linkedin']):
                        score -= 10
                    
                    if score > best_score:
                        best_score = score
                        best_index = i
                
                print(f"[🎯] Fallback selected element {best_index} with score {best_score}")
            
            # Get the text of the best element
            best_element_text = elements[best_index].get('text', '') if best_index < len(elements) else ""
            
            return {
                "best_element_index": best_index,
                "confidence": result.get('confidence', 0),
                "reasoning": reasoning,
                "element_text": best_element_text
            }

        except Exception as e:
            print(f"[!] Error in form navigation analysis: {str(e)}")
            return {
                "best_element_index": -1,
                "confidence": 0,
                "reasoning": f"Error: {str(e)}",
                "element_text": ""
            }

class DynamicWeb:
    def __init__(self,cap_api,api_key,user_data=None):
        self.sitekey = None
        self.data = None
        self.web = None
        self.Cap_API = cap_api
        self.form_analyzer = FormAnalyzer(api_key)
        self.field_mapper = FormFieldMapper(user_data=user_data)
        self.sentiment_analyzer = SentimentAnalyzer(api_key)
        self.navigation_agent = FormNavigationAgent(api_key)

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
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(self.web)
            
            # Try multiple selectors for site key
            site_key_selectors = [
                ".g-recaptcha[data-sitekey]",
                "[data-sitekey]",
                "iframe[title='reCAPTCHA']",
                ".g-recaptcha",
                "[class*='recaptcha']"
            ]
            
            for selector in site_key_selectors:
                try:
                    # Check if element exists
                    element = page.locator(selector)
                    if await element.count() > 0:
                        # Try to get site key from data-sitekey attribute
                        site_key = await element.first.get_attribute("data-sitekey")
                        if site_key:
                            print(f"[🔑] Found site key: {site_key}")
                            await browser.close()
                            return site_key
                        
                        # Try to get from iframe src
                        iframe_src = await element.first.get_attribute("src")
                        if iframe_src and "recaptcha" in iframe_src:
                            # Extract site key from URL
                            import re
                            match = re.search(r'k=([^&]+)', iframe_src)
                            if match:
                                site_key = match.group(1)
                                print(f"[🔑] Found site key from iframe: {site_key}")
                                await browser.close()
                                return site_key
                except Exception as e:
                    print(f"[!] Error with selector {selector}: {str(e)}")
                    continue
            
            print("[!] Could not find site key")
            await browser.close()
            return None

    async def load_page_with_retry(self, page, url: str, max_retries: int = 3) -> bool:
        """Load page with retry logic and multiple strategies."""
        for attempt in range(max_retries):
            try:
                print(f"[🔄] Loading attempt {attempt + 1}/{max_retries}")
                
                # Strategy 1: Try with domcontentloaded + JavaScript dependencies
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    # Wait for JavaScript dependencies
                    await page.wait_for_function("""
                        () => {
                            // Wait for common JS frameworks to load
                            return (
                                (typeof jQuery === 'undefined' || jQuery.ready) &&
                                (typeof React === 'undefined' || React) &&
                                (typeof angular === 'undefined' || angular.element) &&
                                (typeof Vue === 'undefined' || Vue) &&
                                document.readyState === 'complete'
                            );
                        }
                    """, timeout=20000)
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    print("[✓] Page loaded with domcontentloaded + JS dependencies strategy")
                    return True
                except Exception as e:
                    print(f"[!] domcontentloaded + JS strategy failed: {str(e)}")
                
                # Strategy 2: Try with load event + extended JS wait
                try:
                    await page.goto(url, wait_until="load", timeout=30000)
                    # Wait for all JavaScript to execute
                    await page.wait_for_function("""
                        () => {
                            return new Promise((resolve) => {
                                if (document.readyState === 'complete') {
                                    // Wait a bit more for any delayed scripts
                                    setTimeout(resolve, 2000);
                                } else {
                                    window.addEventListener('load', () => {
                                        setTimeout(resolve, 2000);
                                    });
                                }
                            });
                        }
                    """, timeout=25000)
                    print("[✓] Page loaded with load + extended JS wait strategy")
                    return True
                except Exception as e:
                    print(f"[!] load + extended JS strategy failed: {str(e)}")
                
                # Strategy 3: Try without wait_until + comprehensive JS check
                try:
                    await page.goto(url, timeout=30000)
                    # Comprehensive JavaScript dependency check
                    await page.wait_for_function("""
                        () => {
                            return new Promise((resolve) => {
                                const checkJS = () => {
                                    // Check if all common frameworks are loaded
                                    const frameworksLoaded = (
                                        (typeof jQuery === 'undefined' || jQuery.ready) &&
                                        (typeof React === 'undefined' || React) &&
                                        (typeof angular === 'undefined' || angular.element) &&
                                        (typeof Vue === 'undefined' || Vue) &&
                                        (typeof bootstrap === 'undefined' || bootstrap) &&
                                        (typeof moment === 'undefined' || moment) &&
                                        document.readyState === 'complete'
                                    );
                                    
                                    if (frameworksLoaded) {
                                        resolve(true);
                                    } else {
                                        setTimeout(checkJS, 500);
                                    }
                                };
                                checkJS();
                            });
                        }
                    """, timeout=30000)
                    print("[✓] Page loaded with comprehensive JS check strategy")
                    return True
                except Exception as e:
                    print(f"[!] comprehensive JS check strategy failed: {str(e)}")
                
                # Strategy 4: Try with commit + minimal JS wait
                try:
                    await page.goto(url, wait_until="commit", timeout=30000)
                    await page.wait_for_selector('body', timeout=15000)
                    # Minimal JavaScript wait
                    await page.wait_for_function("document.readyState === 'complete'", timeout=10000)
                    print("[✓] Page loaded with commit + minimal JS strategy")
                    return True
                except Exception as e:
                    print(f"[!] commit + minimal JS strategy failed: {str(e)}")
                
            except Exception as e:
                print(f"[!] Attempt {attempt + 1} completely failed: {str(e)}")
                if attempt < max_retries - 1:
                    print(f"[⏳] Waiting 3 seconds before retry...")
                    await page.wait_for_timeout(3000)
        
        return False

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
            
            # Handle iframe forms
            if key == 'iframe':
                print(f"[🔍] Filling iframe form: {value}")
                
                # Find the iframe
                iframe = page.locator(f'iframe#{value}').first
                if await iframe.count() == 0:
                    # Try by title
                    iframe = page.locator(f'iframe[title*="{value}"]').first
                if await iframe.count() == 0:
                    # Try by src containing the value
                    iframe = page.locator(f'iframe[src*="{value}"]').first
                
                if await iframe.count() == 0:
                    print("[!] Could not find iframe")
                    return False
                
                # Switch to iframe context
                frame = await iframe.content_frame()
                if not frame:
                    print("[!] Could not access iframe content")
                    return False
                
                print("[✓] Switched to iframe context")
                
                # Get all form elements in the iframe
                form_elements = await frame.query_selector_all('''
                    input:not([type="submit"]):not([type="hidden"]),
                    select,
                    textarea
                ''')
                
                if not form_elements:
                    print("[!] No form elements found in iframe")
                    return False
                    
                print(f"[✓] Found {len(form_elements)} form elements in iframe")
                
                # Fill the form elements in iframe
                for element in form_elements:
                    try:
                        # Get element type
                        element_type = await element.evaluate('el => el.tagName.toLowerCase()')
                        
                        if element_type == 'select':
                            # Handle dropdown selection
                            await self.handle_dropdown_selection_in_frame(frame, element)
                            continue
                            
                        # Get field attributes
                        field_name = await element.get_attribute('name')
                        field_id = await element.get_attribute('id')
                        placeholder = await element.get_attribute('placeholder')
                        
                        # Map the field to a value
                        field_type, value = self.field_mapper.map_field(field_name, field_id, placeholder)
                        
                        if field_type and value:
                            # Fill the field in iframe
                            await element.fill(value)
                            print(f"[✓] Filled {field_type} field in iframe with value: {value}")
                            
                            # Handle special cases
                            if field_type == 'message' and element_type == 'textarea':
                                await element.fill(value)
                                print(f"[✓] Filled textarea in iframe with message: {value}")
                                
                    except Exception as e:
                        print(f"[!] Error filling iframe field: {str(e)}")
                        continue
                
                return True
            
            # Handle regular forms
            else:
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

            return all_fields_filled

        except Exception as e:
            print(f"[!] Error in fill_form: {str(e)}")
            return False

    async def handle_dropdown_selection_in_frame(self, frame, element) -> bool:
        """Handle dropdown selection in iframe context."""
        try:
            print("[🔍] Processing dropdown selection in iframe...")
            
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
            print(f"[!] Error handling dropdown selection in iframe: {str(e)}")
            return False

    async def check_for_captcha(self, page) -> bool:
        """Check if there's a solvable CAPTCHA on the page."""
        try:
            print("[🔍] Checking for CAPTCHA...")
            
            # Check for text-only CAPTCHA warnings first (not solvable)
            text_only_captcha_selectors = [
                '[class*="recaptcha_v3"]',
                '[class*="g-recaptcha"]',
                '[data-sitekey][data-type="v3"]',
                '[data-sitekey][data-size="invisible"]',
                '.elementor-field-type-recaptcha_v3',
                '.grecaptcha-badge',
                '[data-badge="bottomright"]',
                '[data-size="invisible"]'
            ]
            
            for selector in text_only_captcha_selectors:
                try:
                    elements = page.locator(selector)
                    if await elements.count() > 0:
                        # Check if it's just a warning/display element
                        is_warning_only = await page.evaluate(f"""
                            () => {{
                                const elements = document.querySelectorAll('{selector}');
                                for (let el of elements) {{
                                    // Check if it's reCAPTCHA v3 (invisible/warning only)
                                    const dataType = el.getAttribute('data-type');
                                    const dataSize = el.getAttribute('data-size');
                                    const dataBadge = el.getAttribute('data-badge');
                                    const isV3 = dataType === 'v3' || dataSize === 'invisible' || dataBadge === 'bottomright';
                                    
                                    // Check if it's just a badge/warning
                                    const isBadge = el.classList.contains('grecaptcha-badge') || 
                                                   el.classList.contains('elementor-field-type-recaptcha_v3') ||
                                                   isV3;
                                    
                                    // Check if it has any interactive elements
                                    const hasInteractive = el.querySelector('input[type="checkbox"]') ||
                                                          el.querySelector('button:not(.grecaptcha-logo)') ||
                                                          el.querySelector('iframe[src*="api2/anchor"]');
                                    
                                    return isBadge && !hasInteractive;
                                }}
                                return false;
                            }}
                        """)
                        
                        if is_warning_only:
                            print(f"[ℹ️] Found text-only CAPTCHA warning (not solvable): {selector}")
                            # Don't return True for warning-only captchas
                            continue
                            
                except Exception as e:
                    print(f"[!] Error checking text-only CAPTCHA: {str(e)}")
                    continue
            
            # Check for solvable CAPTCHA elements (exclude v3)
            captcha_selectors = [
                'iframe[title="reCAPTCHA"]:not([data-type="v3"])',
                'iframe[src*="recaptcha/api2/anchor"]',
                'iframe[src*="recaptcha/api2/bframe"]',
                'iframe[src*="recaptcha/enterprise/anchor"]',
                'iframe[src*="recaptcha/enterprise/bframe"]',
                '.g-recaptcha iframe:not([data-size="invisible"])',
                'iframe[src*="challenges.cloudflare.com"]',
                'iframe[src*="hcaptcha"]',
                '.h-captcha',
                '[data-sitekey][data-callback]:not([data-type="v3"])'
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
                                
                            # Check for reCAPTCHA v3 (invisible/warning only)
                            is_recaptcha_v3 = await element.evaluate("""
                                (el) => {
                                    // Check if it's reCAPTCHA v3 (invisible)
                                    const dataType = el.getAttribute('data-type');
                                    const dataSize = el.getAttribute('data-size');
                                    const dataBadge = el.getAttribute('data-badge');
                                    
                                    return dataType === 'v3' || dataSize === 'invisible' || dataBadge === 'bottomright';
                                }
                            """)
                            
                            if is_recaptcha_v3:
                                print(f"[ℹ️] Found reCAPTCHA v3 (invisible/warning only): {selector}")
                                # Don't return True for v3 as it's not solvable
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
            print("[🔍] Looking for navigation buttons that lead to forms...")
            
            # Get all clickable elements with their text content
            all_clickable_elements = await page.evaluate("""
                () => {
                    const elements = [];
                    
                    // Get all potential clickable elements
                    const selectors = [
                        'button',
                        'a[href]',
                        '[role="button"]',
                        'input[type="button"]',
                        'input[type="submit"]',
                        '.btn',
                        '.button',
                        '[class*="btn"]',
                        '[class*="button"]',
                        '[class*="cta"]',
                        '[class*="submit"]',
                        '[class*="send"]',
                        '[class*="request"]',
                        '[class*="quote"]',
                        '[class*="contact"]',
                        '[class*="estimate"]'
                    ];
                    
                    selectors.forEach(selector => {
                        const found = document.querySelectorAll(selector);
                        found.forEach(el => {
                            if (el.offsetParent !== null) { // Check if visible
                                const text = el.textContent || el.innerText || '';
                                const className = el.className || '';
                                const id = el.id || '';
                                
                                elements.push({
                                    tagName: el.tagName,
                                    text: text.trim(),
                                    className: className,
                                    id: id,
                                    selector: selector,
                                    isVisible: true
                                });
                            }
                        });
                    });
                    
                    return elements;
                }
            """)
            
            print(f"[ℹ️] Found {len(all_clickable_elements)} potential clickable elements")
            
            if not all_clickable_elements:
                print("[!] No clickable elements found")
                return False
            
            # Use the FormNavigationAgent to analyze and find the best element
            print("[🤖] Using AI agent to analyze navigation elements...")
            analysis_result = await self.navigation_agent.analyze_navigation_elements(all_clickable_elements)
            best_index = analysis_result.get('best_element_index', -1)
            confidence = analysis_result.get('confidence', 0)
            reasoning = analysis_result.get('reasoning', '')
            element_text = analysis_result.get('element_text', '')
            
            print(f"[📊] AI Analysis Results:")
            print(f"  - Best Element Index: {best_index}")
            print(f"  - Confidence: {confidence}%")
            print(f"  - Reasoning: {reasoning}")
            print(f"  - Element Text: '{element_text}'")
            
            if best_index >= 0 and best_index < len(all_clickable_elements):
                # Try to click the best element identified by the agent
                best_element = all_clickable_elements[best_index]
                print(f"[🎯] Attempting to click AI-selected element: '{best_element['text']}'")
                
                try:
                    # Try multiple click strategies for the selected element
                    selector = best_element['selector']
                    element_text = best_element['text']
                    tag_name = best_element['tagName'].lower()
                    
                    print(f"[🎯] Attempting to click {tag_name} element: '{element_text}'")
                    
                    # Strategy 1: Scroll into view and click with force
                    try:
                        element = page.locator(selector).filter(has_text=element_text)
                        if await element.count() > 0:
                            # Scroll element into view first
                            await element.first.scroll_into_view_if_needed()
                            await page.wait_for_timeout(1000)  # Wait for scroll to complete
                            
                            # Try clicking with force
                            await element.first.click(force=True, timeout=10000)
                            print(f"[✓] Successfully clicked AI-selected element: {element_text}")
                            return True  
                    except Exception as e:
                     print(f"[!] Strategy 1 failed: {str(e)}")
                    
                    # Strategy 2: Click by text with scroll
                    try:
                        # Scroll to element first
                        await page.evaluate(f"""
                            const element = document.evaluate(
                                "//a[contains(text(), '{element_text}')] | //button[contains(text(), '{element_text}')]",
                                document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
                            ).singleNodeValue;
                            if (element) {{
                                element.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                            }}
                        """)
                        await page.wait_for_timeout(1000)
                        
                        await page.click(f"text={element_text}", force=True, timeout=10000)
                        print(f"[✓] Successfully clicked AI-selected element by text: {element_text}")
                        return True
                    except Exception as e:
                        print(f"[!] Strategy 2 failed: {str(e)}")
                    
                    # Strategy 3: Click by tag and text with JavaScript
                    try:
                        # For links, use expect_navigation
                        if tag_name == 'a':
                            async with page.expect_navigation(wait_until="networkidle"):
                                await page.evaluate(f"""
                                    const elements = document.querySelectorAll('{tag_name}');
                                    for (let el of elements) {{
                                        if (el.textContent.includes('{element_text}')) {{
                                            el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                            el.click();
                                            return true;
                                        }}
                                    }}
                                """)
                        else:
                            # For buttons, just click without navigation wait
                            await page.evaluate(f"""
                                const elements = document.querySelectorAll('{tag_name}');
                                for (let el of elements) {{
                                    if (el.textContent.includes('{element_text}')) {{
                                        el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                        el.click();
                                        return true;
                                    }}
                                }}
                            """)
                            await page.wait_for_timeout(2000)
                        
                        print(f"[✓] Successfully clicked AI-selected element by JavaScript: {element_text}")
                        return True
                    except Exception as e:
                        print(f"[!] Strategy 3 failed: {str(e)}")
                    
                    # Strategy 4: Click by href for links with proper navigation (including sliders/carousels)
                    if tag_name == 'a':
                        try:
                            # Get the href first
                            href_result = await page.evaluate(f"""
                                const link = document.querySelector('a[href*="/contact"], a[href*="/quote"], a[href*="/request"], a[href*="/form"]');
                                if (link && link.textContent.includes('{element_text}')) {{
                                    return link.href;
                                }}
                                return null;
                            """)
                            
                            if href_result:
                                print(f"[🔗] Found link with href: {href_result}")
                                
                                # Method 1: Handle slider/carousel navigation
                                try:
                                    print("[🎠] Attempting slider/carousel navigation...")
                                    
                                    # Check if we're in a slider/carousel context
                                    slider_result = await page.evaluate(f"""
                                        // Find the link in slider/carousel context
                                        const link = document.querySelector('a[href="{href_result}"]');
                                        if (link) {{
                                            // Check if link is in a slider/carousel
                                            let parent = link.parentElement;
                                            let isInSlider = false;
                                            let sliderContainer = null;
                                            
                                            while (parent && parent !== document.body) {{
                                                const className = parent.className || '';
                                                const id = parent.id || '';
                                                
                                                if (className.includes('slider') || className.includes('carousel') || 
                                                    className.includes('swiper') || className.includes('slick') ||
                                                    id.includes('slider') || id.includes('carousel')) {{
                                                    isInSlider = true;
                                                    sliderContainer = parent;
                                                    break;
                                                }}
                                                parent = parent.parentElement;
                                            }}
                                            
                                            if (isInSlider) {{
                                                // Ensure the slide with the link is active/visible
                                                link.scrollIntoView({{ behavior: 'smooth', block: 'center', inline: 'center' }});
                                                
                                                // Wait a bit for any animations
                                                setTimeout(() => {{
                                                    // Try to make the link visible and clickable
                                                    link.style.display = 'block';
                                                    link.style.visibility = 'visible';
                                                    link.style.opacity = '1';
                                                    link.style.zIndex = '9999';
                                                    
                                                    // Click the link
                                                    link.click();
                                                }}, 1000);
                                                
                                                return true;
                                            }} else {{
                                                // Regular link, just click it
                                                link.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                                link.click();
                                                return true;
                                            }}
                                        }}
                                        return false;
                                    """)
                                    
                                    if slider_result:
                                        await page.wait_for_load_state("networkidle")
                                        await page.wait_for_timeout(2000)
                                        print(f"[✓] Successfully handled slider/carousel navigation: {element_text}")
                                        return True
                            
                                except Exception as e:
                                    print(f"[!] Slider navigation failed: {str(e)}")
                                
                                # Method 2: Direct navigation with full URL
                                try:
                                    current_url = page.url
                                    base_url = current_url.rstrip('/')
                                    if href_result.startswith('/'):
                                        full_url = base_url + href_result
                                    else:
                                        full_url = href_result
                                    
                                    print(f"[🔗] Attempting direct navigation to: {full_url}")
                                    await page.goto(full_url, wait_until="networkidle")
                                    print(f"[✓] Successfully navigated to: {full_url}")
                                    return True
                                except Exception as e:
                                    print(f"[!] Direct navigation failed: {str(e)}")
                                
                                # Method 3: Click the link and wait for navigation
                                try:
                                    element = page.locator(f'a[href="{href_result}"]')
                                    if await element.count() > 0:
                                        # Wait for navigation to start
                                        async with page.expect_navigation(wait_until="networkidle"):
                                            await element.first.click()
                                        print(f"[✓] Successfully clicked link and navigated: {element_text}")
                                        return True
                                except Exception as e:
                                    print(f"[!] Click navigation failed: {str(e)}")
                                
                                # Method 4: JavaScript click with navigation wait
                                try:
                                    await page.evaluate(f"""
                                        const link = document.querySelector('a[href="{href_result}"]');
                                        if (link) {{
                                            link.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                            link.click();
                                        }}
                                    """)
                                    await page.wait_for_load_state("networkidle")
                                    print(f"[✓] Successfully clicked link via JavaScript: {element_text}")
                                    return True
                                except Exception as e:
                                    print(f"[!] JavaScript click failed: {str(e)}")
                            
                        except Exception as e:
                            print(f"[!] Strategy 4 failed: {str(e)}")
                    
                    # Strategy 5: Click by class if available
                    if best_element['className']:
                        try:
                            class_selector = f"{tag_name}.{best_element['className'].replace(' ', '.')}"
                            element = page.locator(class_selector)
                            if await element.count() > 0:
                                await element.first.scroll_into_view_if_needed()
                                await page.wait_for_timeout(1000)
                                await element.first.click(force=True, timeout=10000)
                                print(f"[✓] Successfully clicked AI-selected element by class: {element_text}")
                                return True
                        except Exception as e:
                            print(f"[!] Strategy 5 failed: {str(e)}")
                    
                    # Strategy 6: Handle horizontally scrollable containers
                    try:
                        await page.evaluate(f"""
                            const element = document.querySelector('{tag_name}[href*="/contact"], {tag_name}[href*="/quote"], {tag_name}[href*="/request"], {tag_name}[href*="/form"]');
                            if (element && element.textContent.includes('{element_text}')) {{
                                // Find the scrollable parent container
                                let parent = element.parentElement;
                                while (parent && parent !== document.body) {{
                                    const style = window.getComputedStyle(parent);
                                    if (style.overflowX === 'auto' || style.overflowX === 'scroll' || 
                                        style.overflow === 'auto' || style.overflow === 'scroll') {{
                                        // Scroll the container to make element visible
                                        const rect = element.getBoundingClientRect();
                                        const parentRect = parent.getBoundingClientRect();
                                        
                                        if (rect.left < parentRect.left) {{
                                            parent.scrollLeft -= (parentRect.left - rect.left + 50);
                                        }} else if (rect.right > parentRect.right) {{
                                            parent.scrollLeft += (rect.right - parentRect.right + 50);
                                        }}
                                        break;
                                    }}
                                    parent = parent.parentElement;
                                }}
                                
                                // Also scroll the element itself into view
                                element.scrollIntoView({{ behavior: 'smooth', block: 'center', inline: 'center' }});
                                
                                // Wait a bit then click
                                setTimeout(() => {{
                                    element.click();
                                }}, 1000);
                            }}
                        """)
                        await page.wait_for_timeout(2000)
                        print(f"[✓] Successfully clicked element in scrollable container: {element_text}")
                        return True
                    except Exception as e:
                        print(f"[!] Strategy 6 failed: {str(e)}")
                    
                    # Strategy 7: Force click with JavaScript (bypass viewport checks)
                    try:
                        await page.evaluate(f"""
                            const elements = document.querySelectorAll('{tag_name}');
                            for (let el of elements) {{
                                if (el.textContent.includes('{element_text}')) {{
                                    // Force click without viewport checks
                                    el.dispatchEvent(new MouseEvent('click', {{
                                        bubbles: true,
                                        cancelable: true,
                                        view: window
                                    }}));
                                    return true;
                                }}
                            }}
                        """)
                        await page.wait_for_timeout(2000)
                        print(f"[✓] Successfully force-clicked element via JavaScript: {element_text}")
                        return True
                    except Exception as e:
                        print(f"[!] Strategy 7 failed: {str(e)}")
                    
                    print(f"[!] All click strategies failed for AI-selected element: {element_text}")
                    
                except Exception as e:
                 print(f"[!] Error clicking AI-selected element: {str(e)}")
            else:
                print("[!] AI agent could not identify a suitable navigation element")
            
            print("[!] No suitable navigation button found")
            return False
            
        except Exception as e:
            print(f"[!] Error in navigation button detection: {str(e)}")
            return False

    async def find_form_elements(self, page) -> bool:
        """Find form elements on the page using multiple detection strategies."""
        try:
            print("[🔍] Searching for form relevant button...")
            form_btn = page.locator("button").filter(has_text=re.compile(
                    r"Submit | Send Message | Pay Now |get a free Estimate Now|Register|Request a free estimation|"
                    r"Request a free quote|Contact\s*us|Get Quotation|Call",
                    re.IGNORECASE))
            ##find button with given text inside to track towards the form using the button
            buttons = await form_btn.all()
            ##first here it will check for form elemetns using buttons , if none found , will move to next strategy
            if buttons:
                for btn in buttons:
                    
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

            # Strategy 2: Check for iframe forms (like JotForm)
            print("[🔍] Checking for iframe forms...")
            try:
                # Wait for iframes to load
                await page.wait_for_timeout(2000)
                
                iframe_elements = await page.query_selector_all('iframe')
                print(f"[ℹ️] Found {len(iframe_elements)} iframes using query_selector_all")
                
                # Also try with locator
                iframe_locator = page.locator('iframe')
                iframe_count = await iframe_locator.count()
                print(f"[ℹ️] Found {iframe_count} iframes using locator")
                
                # List all iframes for debugging
                for i in range(iframe_count):
                    iframe = iframe_locator.nth(i)
                    iframe_id = await iframe.get_attribute('id')
                    iframe_title = await iframe.get_attribute('title')
                    iframe_src = await iframe.get_attribute('src')
                    # print(f"[ℹ️] Iframe {i+1}: id='{iframe_id}', title='{iframe_title}', src='{iframe_src}'")
                
                for iframe in iframe_elements:
                    try:
                        # Check if iframe is visible
                        is_visible = await iframe.is_visible()
                        print(f"[ℹ️] Iframe visibility: {is_visible}")
                        
                        if not is_visible:
                            continue
                            
                        # Get iframe attributes
                        iframe_id = await iframe.get_attribute('id')
                        iframe_title = await iframe.get_attribute('title')
                        iframe_src = await iframe.get_attribute('src')
                        
                        print(f"[ℹ️] Checking iframe: id='{iframe_id}', title='{iframe_title}', src='{iframe_src}'")
                        
                        # Check if this looks like a form iframe
                        form_indicators = ['form', 'jotform', 'quote', 'request', 'contact', 'submit']
                        iframe_text = f"{iframe_id or ''} {iframe_title or ''} {iframe_src or ''}".lower()
                        
                        print(f"[ℹ️] Iframe text for analysis: {iframe_text}")
                        
                        # Special check for JotForm
                        is_jotform = 'jotform' in iframe_src.lower() if iframe_src else False
                        print(f"[ℹ️] Is JotForm iframe: {is_jotform}")
                        
                        if is_jotform or any(indicator in iframe_text for indicator in form_indicators):
                            print(f"[✓] Found potential form iframe: {iframe_title}")
                            
                            # For JotForm, we know it's a form, so return immediately
                            if is_jotform:
                                print(f"[✓] JotForm iframe detected: {iframe_id}")
                                identifier = ('iframe', iframe_id or iframe_title or 'jotform-iframe')
                                return identifier
                            
                            # Wait for iframe to load
                            try:
                                # Wait for iframe to be ready
                                await iframe.wait_for_element_state('attached', timeout=5000)
                                
                                # Try to access the iframe content
                                frame = await iframe.content_frame()
                                if frame:
                                    print(f"[✓] Successfully accessed iframe content")
                                    
                                    # Wait a bit for iframe content to load
                                    await page.wait_for_timeout(2000)
                                    
                                    # Check for forms inside the iframe
                                    iframe_forms = await frame.query_selector_all('form')
                                    if iframe_forms:
                                        print(f"[✓] Found {len(iframe_forms)} forms inside iframe")
                                        
                                        # Return iframe identifier
                                        identifier = ('iframe', iframe_id or iframe_title or 'form-iframe')
                                        return identifier
                                    
                                    # Check for form-like elements inside iframe
                                    form_inputs = await frame.query_selector_all('input, select, textarea')
                                    if form_inputs and len(form_inputs) >= 3:
                                        print(f"[✓] Found {len(form_inputs)} form inputs inside iframe")
                                        
                                        # Return iframe identifier
                                        identifier = ('iframe', iframe_id or iframe_title or 'form-iframe')
                                        return identifier
                                        
                            except Exception as e:
                                print(f"[!] Error accessing iframe content: {str(e)}")
                                continue
                                
                    except Exception as e:
                        print(f"[!] Error checking iframe: {str(e)}")
                        continue
                        
            except Exception as e:
                print(f"[!] Error checking iframes: {str(e)}")


            # Strategy 3: Check for form-like structures using Readability.js approach
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
                    
                    # Verify at least one container is a valid form (must have more than 2 inputs)
                    valid_containers = [c for c in form_containers if c['hasInputs'] > 2 and c['hasSubmit'] and c['isVisible']]
                    if valid_containers:
                        print("[✓] Found valid form-like structure")
                        # Return the first valid container
                        container = valid_containers[0]
                        form_id = container['id']
                        form_class = container['className']
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

            # Set realistic browser headers to avoid bot detection
            await page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            })

            # Navigate to the page with retry logic
            success = await self.load_page_with_retry(page, url)
            if not success:
                print(f"[!] Failed to load page after retries: {url}")
                return False
                
            print("[✓] Page loaded successfully")
            

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
                
                # Handle page context after button click
                context_success, page = await self.handle_page_context_after_button_click(page, success)
                
                if not context_success:
                    print("[!] Failed to handle page context after button click")
                    return False
                
                print(f"[✓] Using target page for form detection: {page.url}")

                try:
                    form_found = await self.find_form_elements(page)
                    if form_found:
                        # Fill the form on the new page
                        success = await self.fill_form(page,form_found)
                        
                        if not success:
                            print("[!] Failed to fill form")
                            return False
                    else:
                        print("[!] No form found on target page")
                        return False
                    
                except Exception as e:
                    print(f"[!] Error finding form on target page: {str(e)}")
                    return False
            
            # Submit the form (use target_page if available, otherwise use original page)
            submit_page = page if 'page' in locals() else page
            success = await self.submit_form('input[type="submit"]', url, submit_page, form_found)
            if not success:
                print("[!] Form submission failed or could not be verified")
                return False
            
            print("[✓] Form processed successfully")
            return {"status": "success", "message": "[✓] Form processed successfully"}
            
        except Exception as e:
            print(f"[!] Error processing URL {url}: {str(e)}")
            return {"status": "error", "message": str(e)}

    async def submit_form(self, selector: str,url, page, identifier, parent_div=None) -> bool:
        """Submit the form and verify the submission.
            Will  add parent div button check case later on"""
        try:
            print("[🔍] Monitoring Form Submission")
            
            # Get the initial URL
            initial_url = page.url
            key , value = identifier
            
            # First, try to find submit button within the specific form identified by the identifier
            submit_button = None
            
            # Define submit button selectors to try
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
            
            # Strategy 1: Use AI-powered button detection to find submit button
            print(f"[🎯] Using AI analyzer to find submit button for form identified by {key}: {value}")
            
            # Set up network request monitoring
            requests_log = []
            
            async def log_request(route):
                request = route.request
                requests_log.append({
                    'url': request.url,
                    'method': request.method,
                    'headers': dict(request.headers),
                    'post_data': request.post_data
                })
                print(f"[📡] Request: {request.method} {request.url}")
                await route.continue_()
            
            # Start monitoring network requests
            await page.route("**", log_request)
            
            # Set up MutationObserver before button click to track DOM changes
            print("[🔍] Setting up MutationObserver to track DOM changes...")
            await page.evaluate("""
                () => {
                    window._formSubmitTime = Date.now();
                    window._mutationLogs = [];
                    
                    const observer = new MutationObserver((mutations) => {
                        for (let m of mutations) {
                            for (let node of m.addedNodes) {
                                if (!node.textContent || typeof node.textContent !== "string") continue;
                                
                                window._mutationLogs.push({
                                    text: node.textContent.trim(),
                                    time: Date.now()
                                });
                            }
                        }
                    });
                    
                    observer.observe(document.body, { 
                        childList: true, 
                        subtree: true 
                    });
                    
                    console.log('MutationObserver set up successfully');
                }
            """)
            
            # Use the AI-powered find_button function to detect submit buttons
            ai_button_success = await self.find_button(page)
            
            if ai_button_success:
                print("[✓] AI analyzer found and clicked a submit button")
                
                # Monitor network requests to see what URLs are being requested
                print("[📡] Monitoring network requests after button click...")
                
                # Wait for any navigation or form submission to complete
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(2000)
                
                # Check if the button click resulted in a form submission
                current_url = page.url
                print(f"[🔍] Current URL after AI button click: {current_url}")
                
                # Get all recent network requests
                try:
                    # Check captured network requests
                    print(f"[📊] Total requests captured: {len(requests_log)}")
                    for i, req in enumerate(requests_log):
                        print(f"[📡] Request {i+1}: {req['method']} {req['url']}")
                        if req['post_data']:
                            print(f"[📡] Post data: {req['post_data'][:200]}...")
                    
                    # Check current page state
                    page_title = await page.title()
                    print(f"[📄] Page title: {page_title}")

                    
                except Exception as e:
                    print(f"[!] Error monitoring page state: {str(e)}")
                
                # Check for form submission indicators
                try:
                    # Look for success/error messages
                    success_indicators = [
                        'text="Thank you"',
                        'text="Success"',
                        'text="Submitted"',
                        'text="Message sent"',
                        'text="Form submitted"',
                        '[class*="success"]',
                        '[class*="thank"]'
                    ]
                    
                    for indicator in success_indicators:
                        if await page.locator(indicator).count() > 0:
                            print(f"[✓] Found success indicator: {indicator}")
                            return True
                    
                    # Check if URL changed (indicating form submission)
                    if current_url != initial_url:
                        print(f"[✓] URL changed from {initial_url} to {current_url}")
                        return True
                    
                    # Check for form submission response
                    try:
                        # Look for any response content that might indicate success
                        page_content = await page.content()
                        if any(word in page_content.lower() for word in ['thank', 'success', 'submitted', 'sent']):
                            print("[✓] Found success keywords in page content")
                            return True
                    except Exception as e:
                        print(f"[!] Error checking page content: {str(e)}")
                    
                    print("[ℹ️] AI button click completed, but no clear success indicators found")
                    return True  # Assume success if no clear failure indicators
                    
                except Exception as e:
                    print(f"[!] Error checking form submission result: {str(e)}")
                    return True  # Assume success if we can't determine
            else:
                print("[!] AI analyzer could not find a suitable submit button")
            
            # Fallback: Try traditional form-specific button detection
            print("[🔄] Falling back to traditional form-specific button detection...")
            
            for sel in submit_selectors:
                try:
                    if key == 'id':
                        # Look for submit button within the form with specific ID
                        form_selector = f'form#{value}'
                        button_selector = f'form#{value} {sel}'
                    elif key == 'class':
                        # Look for submit button within the form with specific class
                        form_selector = f'form.{value.strip().split()[0]}'
                        button_selector = f'form.{value.strip().split()[0]} {sel}'
                    elif key == 'iframe':
                        # For iframe forms, look within the iframe
                        print(f"[🖼️] Looking for submit button within iframe: {value}")
                        # Try to find iframe and access its content
                        iframe = page.locator(f'iframe#{value}, iframe[title="{value}"]')
                        if await iframe.count() > 0:
                            frame = await iframe.first.content_frame()
                            if frame:
                                # Look for submit button within the iframe
                                for iframe_sel in submit_selectors:
                                    try:
                                        iframe_button = frame.locator(iframe_sel)
                                        if await iframe_button.count() > 0:
                                            # Check if button is visible
                                            is_visible = await iframe_button.first.is_visible()
                                            if is_visible:
                                                submit_button = iframe_button.first
                                                print(f"[✓] Found visible submit button in iframe with selector: {iframe_sel}")
                                                break
                                    except Exception:
                                        continue
                                if submit_button:
                                    break
                        continue
                    else: 
                        continue
                   
                    # Look for submit button within the form
                    button = page.locator(button_selector)

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
                            submit_button = button.first
                            print(f"[✓] Found visible submit button within form with selector: {sel}")
                            break
                except Exception as e:
                    print(f"[!] Error checking selector {sel}: {str(e)}")
                    continue
            
            if not submit_button:
                print("[!] No visible submit button found anywhere on the page")
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
           
            
            # print(f"[📡] Form method: {form_info['method']}")
            # print(f"[📡] Has submit handler: {form_info['hasSubmitHandler']}")

            async def check_success_indicators(response_status=None):
                """Check various success indicators and return probability of successful submission"""
                indicators = {
                    'response_status': 0,
                    'url_change': 0,
                    'message': 0,
                    'mutation': 0  # New indicator for DOM changes
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

                # === Check for DOM changes using MutationObserver ===
                try:
                    print("[🔍] Checking for DOM changes using MutationObserver...")
                    
                    # Check if MutationObserver logs exist
                    mutation_analysis = await page.evaluate("""
                        () => {
                            const logs = window._mutationLogs || [];
                            const submitTime = window._formSubmitTime || 0;
                            
                            if (logs.length === 0) {
                                return { hasLogs: false, message: "No mutation logs found" };
                            }
                            
                            // Filter logs that appeared after form submission
                            const relevantLogs = logs.filter(log => 
                                log.time > submitTime && 
                                log.text.length > 0
                            );
                            
                            // Check for success/error messages (Priority 1)
                            const successKeywords = ['thank', 'success', 'submitted', 'sent', 'received', 'confirmation'];
                            const errorKeywords = ['error', 'failed', 'invalid', 'required', 'missing'];
                            
                            let successMessage = null;
                            let errorMessage = null;
                            
                            for (const log of relevantLogs) {
                                const text = log.text.toLowerCase();
                                
                                // Check for success messages
                                if (successKeywords.some(keyword => text.includes(keyword))) {
                                    successMessage = log.text;
                                    break;
                                }
                                
                                // Check for error messages
                                if (errorKeywords.some(keyword => text.includes(keyword))) {
                                    errorMessage = log.text;
                                    break;
                                }
                            }
                            
                            // Check for form fields disappearing (Priority 2)
                            const formFields = document.querySelectorAll('input, textarea, select');
                            const visibleFields = Array.from(formFields).filter(field => {
                                const style = window.getComputedStyle(field);
                                return style.display !== 'none' && 
                                       style.visibility !== 'hidden' && 
                                       style.opacity !== '0' &&
                                       field.offsetParent !== null;
                            });
                            
                            return {
                                hasLogs: true,
                                successMessage: successMessage,
                                errorMessage: errorMessage,
                                visibleFieldsCount: visibleFields.length,
                                totalLogs: relevantLogs.length,
                                logs: relevantLogs.slice(0, 5) // First 5 logs for debugging
                            };
                        }
                    """)
                    
                    if mutation_analysis['hasLogs']:
                        print(f"[📊] Mutation Analysis Results:")
                        print(f"  - Total relevant logs: {mutation_analysis['totalLogs']}")
                        print(f"  - Visible form fields: {mutation_analysis['visibleFieldsCount']}")
                        
                        if mutation_analysis['logs']:
                            print(f"[📝] Recent DOM changes:")
                            for i, log in enumerate(mutation_analysis['logs']):
                                print(f"    {i+1}. '{log['text']}' (at {log['time']})")
                        
                        # Priority 1: Check for success/error messages
                        if mutation_analysis['successMessage']:
                            print(f"[✅] Found success message: '{mutation_analysis['successMessage']}'")
                            indicators['mutation'] = 1
                        elif mutation_analysis['errorMessage']:
                            print(f"[❌] Found error message: '{mutation_analysis['errorMessage']}'")
                            indicators['mutation'] = 0
                        # Priority 2: Check for form fields disappearing
                        elif mutation_analysis['visibleFieldsCount'] == 0:
                            print("[✅] All form fields disappeared - likely successful submission")
                            indicators['mutation'] = 1
                        else:
                            print("[ℹ️] No clear success/error indicators in DOM changes")
                            indicators['mutation'] = 0.5
                    else:
                        print("[ℹ️] No mutation logs found - using traditional indicators")
                        indicators['mutation'] = 0.5
                        
                except Exception as e:
                    print(f"[!] Error in MutationObserver analysis: {str(e)}")
                    indicators['mutation'] = 0.5

                # === Look for success/failure messages (traditional method) ===
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
                    indicators['response_status'] * 0.4 +
                    indicators['url_change'] * 0.2 +
                    indicators['message'] * 0.2 +
                    indicators['mutation'] * 0.2  # Add mutation indicator to final calculation
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

            # CAPTCHA detection - use the enhanced check_for_captcha method
            has_solvable_captcha = await self.check_for_captcha(page)
            
            if has_solvable_captcha:
                print("[🤖] Solvable CAPTCHA detected, attempting to solve...")
                
                # Get site key using the enhanced method
                site_key = await self.site_key(url)
                if not site_key:
                    print("[!] Could not find site key")
                else:
                        print(f"[🔑] Found site key: {site_key}")
                        
                        # Solve CAPTCHA
                        solver = self.Captcha_solver(site_key, url)
                        if not solver:
                            print("[!] Failed to solve CAPTCHA")
                        else:
                        # Set the response
                            try:
                                await page.evaluate(f'''
                                const textarea = document.querySelector("textarea[name='g-recaptcha-response']");
                                if (textarea) {{
                                    textarea.style.display = 'block';
                                    textarea.value = "{solver}";
                                }}
                                ''')
                                print("[✓] CAPTCHA response set")
                            except Exception as e:
                             print(f"[!] Error setting CAPTCHA response: {str(e)}")
            else:
                print("[ℹ️] No solvable CAPTCHA found, proceeding with form submission")

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

    async def handle_page_context_after_button_click(self, page, button_click_success: bool) -> tuple[bool, object]:
        """
        Handle page context after button click and return the appropriate page for form detection.
        Handles new tabs and same-page navigation.
        
        Args:
            page: The original page object
            button_click_success: Boolean indicating if button click was successful
            
        Returns:
            tuple: (success: bool, target_page: object)
        """
        try:
            if not button_click_success:
                print("[!] Button click was not successful")
                return False, page
                            
            await page.wait_for_load_state("networkidle")
            print("[🔍] Checking page context after button click...")
            
            # Debug: Save current page HTML to file
            try:
                html_content = await page.content()
                with open("debug_page_after_click.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                print("[📄] Debug: Page HTML saved to 'debug_page_after_click.html'")
            except Exception as e:
                print(f"[!] Failed to save debug HTML: {str(e)}")
            
            # Get the browser context
            context = page.context
            
            # Wait a bit for any new pages to open
            await page.wait_for_timeout(2000)
            
            # Check for new pages in the same context (new tabs)
            all_pages = context.pages
            print(f"[ℹ️] Total pages in context: {len(all_pages)}")
            
            # Case 1: New page in same context (new tab)
            if len(all_pages) > 1:
                print("[✓] New tab detected!")
                
                # Get the newest page (last in the list)
                new_page = all_pages[-1]
                current_url = new_page.url
                print(f"[✓] New tab URL: {current_url}")
                
                # Switch to the new page
                await new_page.bring_to_front()
                print("[✓] Switched to new tab")
                
                # Wait for the new page to load completely
                await new_page.wait_for_load_state("networkidle")
                await new_page.wait_for_timeout(3000)  # Extra wait for dynamic content
                
                # Debug: Save new page HTML to file
                try:
                    html_content = await new_page.content()
                    with open("debug_new_page_after_click.html", "w", encoding="utf-8") as f:
                        f.write(html_content)
                    print("[📄] Debug: New page HTML saved to 'debug_new_page_after_click.html'")
                except Exception as e:
                    print(f"[!] Failed to save new page debug HTML: {str(e)}")
                
                return True, new_page
            
            # Case 2: No new tab, stay on current page
            else:
                print("[ℹ️] No new tab detected, staying on current page")
                
                # Check if URL changed on current page
                current_url = page.url
                print(f"[ℹ️] Current page URL: {current_url}")
                
                # Wait for any dynamic content to load
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(2000)
                
                return True, page
                
        except Exception as e:
            print(f"[!] Error handling page context: {str(e)}")
            return False, page
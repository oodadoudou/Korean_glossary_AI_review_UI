import openai
import time
import random
import threading
from backend.config_manager import load_config

class AIService:
    def __init__(self):
        self.config = load_config()
        self.providers = [] # List of dicts: {'client': Client, 'model': str, 'name': str, 'key': str}
        self.valid_providers = [] # Subset of providers that passed validation
        self.current_provider_index = 0
        self.reload_config()
        self.rate_limit_pause_event = threading.Event()

    def reload_config(self):
        self.config = load_config()
        self.providers = []
        
        # Check for new 'providers' list structure
        config_providers = self.config.get("providers", [])
        
        # Backward compatibility: Check legacy fields if providers list is empty
        if not config_providers:
            legacy_key = self.config.get("api_key", "")
            legacy_url = self.config.get("base_url", "")
            legacy_model = self.config.get("model", "deepseek-chat")
            
            if legacy_key:
                # Handle multi-line keys in legacy field
                keys = [k.strip() for k in legacy_key.split("\n") if k.strip()]
                for k in keys:
                    config_providers.append({
                        "api_key": k,
                        "base_url": legacy_url,
                        "model": legacy_model
                    })

        # Initialize clients for all providers
        for p in config_providers:
            api_key = p.get("api_key", "").strip()
            base_url = p.get("base_url", "").strip()
            model = p.get("model", "").strip()
            
            if api_key and base_url and model:
                try:
                    client = openai.OpenAI(
                        api_key=api_key,
                        base_url=base_url,
                        timeout=300.0
                    )
                    masked_key = f"{api_key[:8]}..." if len(api_key) > 8 else "KEY"
                    self.providers.append({
                        "client": client,
                        "model": model,
                        "name": f"{model} @ {base_url} ({masked_key})",
                        "api_key": api_key, # Store for validation / reference
                        "base_url": base_url
                    })
                except Exception as e:
                    print(f"Error initializing provider {model}: {e}")

        # Default to all being candidates until validated
        self.valid_providers = list(self.providers)
        self.current_provider_index = 0

    def validate_keys(self, log_callback=None):
        """
        Pre-flight check: Test all providers and filter out invalid ones.
        Returns the number of valid providers found.
        """
        if log_callback:
            log_callback(f"Starting pre-flight validation for {len(self.providers)} providers...")
            
        valid_list = []
        for provider in self.providers:
            name = provider['name']
            try:
                # Create a temporary check client with short timeout
                check_client = openai.OpenAI(
                    api_key=provider['api_key'],
                    base_url=provider['base_url'],
                    timeout=10.0
                )
                
                # Use a unique prompt to prevent caching from upstream proxies
                unique_prompt = f"Hi from review tool check {int(time.time())} {random.randint(1000, 9999)}"
                
                response = check_client.chat.completions.create(
                    model=provider['model'],
                    messages=[{"role": "user", "content": unique_prompt}],
                    max_tokens=5
                )
                
                # Ensure we got a valid response object
                if response and response.choices:
                     valid_list.append(provider)
                     if log_callback:
                        log_callback(f"✅ {name}: Valid")
                else:
                    raise Exception("Empty response from API")

            except Exception as e:
                if log_callback:
                    # Log the full error to help debug 500s "No available credentials"
                    log_callback(f"❌ {name}: Failed - {str(e)}")
        
        self.valid_providers = valid_list
        self.current_provider_index = 0
        
        if not self.valid_providers:
            if log_callback:
                log_callback("CRITICAL: All API providers failed validation!")
            return 0
            
        return len(self.valid_providers)

    def get_next_provider(self):
        if not self.valid_providers:
            raise Exception("No valid API providers available.")
        
        provider = self.valid_providers[self.current_provider_index]
        self.current_provider_index = (self.current_provider_index + 1) % len(self.valid_providers)
        return provider

    def call_api(self, prompt, model=None, log_callback=None):
        if self.rate_limit_pause_event.is_set():
            if log_callback: log_callback("Rate limit hit. Pausing...")
            self.rate_limit_pause_event.wait()

        max_retries = 3
        base_retry_delay = 5

        for attempt in range(max_retries):
            # Rotate provider for each attempt
            try:
                provider = self.get_next_provider()
                client = provider['client']
                # Use provider's specific model unless override provided (which is rare now)
                current_model = provider['model'] 
                provider_name = provider['name']
            except Exception as e:
                err_msg = str(e)
                print(err_msg)
                if log_callback: log_callback(f"Error: {err_msg}")
                return None

            try:
                if log_callback:
                    log_callback(f"Sending request to {provider_name} (Attempt {attempt+1})...")
                    print(f"DEBUG: Sending request to {provider_name}...\n{prompt}") 
                    log_callback(f"--- REQUEST ---\n{prompt}\n----------------")
                    log_callback("Waiting for AI response...")

                response = client.chat.completions.create(
                    model=current_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=8192,
                    temperature=0.1,
                    timeout=300.0 
                )
                content = response.choices[0].message.content
                print(f"DEBUG: Backend received response (len={len(content)})") 
                
                if log_callback:
                    log_callback(f"--- RESPONSE ---\n{content}\n----------------")
                
                return content
            except openai.RateLimitError:
                if log_callback: log_callback("Rate limit error. Retrying...")
                if not self.rate_limit_pause_event.is_set():
                    self.rate_limit_pause_event.set()
                
                wait_time = (base_retry_delay * (2 ** attempt)) + random.uniform(0, 1)
                time.sleep(wait_time)

                if attempt == max_retries - 1:
                    self.rate_limit_pause_event.clear()
            except openai.APITimeoutError:
                err_msg = f"API request timed out (Attempt {attempt+1})."
                print(err_msg)
                if log_callback: log_callback(err_msg)
                if attempt == max_retries - 1:
                    return None
            except Exception as e:
                err_msg = f"API request failed with {provider_name}. Error: {e}"
                print(err_msg)
                if log_callback: log_callback(err_msg)
                # Don't fail immediately, retry with next provider
                if attempt == max_retries - 1:
                    return None
        return None

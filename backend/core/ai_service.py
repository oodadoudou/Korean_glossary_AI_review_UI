import openai
import time
import random
import threading
from backend.config_manager import load_config

class AIService:
    def __init__(self):
        self.config = load_config()
        self.client = None
        self.reload_config()
        self.rate_limit_pause_event = threading.Event()

    def reload_config(self):
        self.config = load_config()
        self.client = openai.OpenAI(
            api_key=self.config.get("api_key"),
            base_url=self.config.get("base_url"),
            timeout=300.0
        )

    def call_api(self, prompt, model=None, log_callback=None):
        if self.rate_limit_pause_event.is_set():
            if log_callback: log_callback("Rate limit hit. Pausing...")
            self.rate_limit_pause_event.wait()

        max_retries = 3
        base_retry_delay = 5
        current_model = model or self.config.get("model", "deepseek-chat")

        for attempt in range(max_retries):
            try:
                if log_callback:
                    log_callback(f"Sending request to {current_model} (Attempt {attempt+1})...")
                    # Log the prompt (truncated if too long to avoid clutter, but user asked for ALL)
                    # User asked: "把所有的AI request 和response都在这个console打印出来"
                    print(f"DEBUG: Sending request to {current_model}...\n{prompt}") # Console print
                    log_callback(f"--- REQUEST ---\n{prompt}\n----------------")
                    log_callback("Waiting for AI response...")

                response = self.client.chat.completions.create(
                    model=current_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=8192,
                    temperature=0.1,
                    timeout=300.0 # Increase timeout to 5 minutes
                )
                content = response.choices[0].message.content
                print(f"DEBUG: Backend received response (len={len(content)})") # Confirm in terminal
                
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
                err_msg = f"API request timed out after 300 seconds (Attempt {attempt+1})."
                print(err_msg)
                if log_callback: log_callback(err_msg)
                if attempt == max_retries - 1:
                    return None
            except Exception as e:
                err_msg = f"API request failed after {max_retries} retries. Error: {e}"
                print(err_msg)
                if log_callback: log_callback(err_msg)
                if attempt == max_retries - 1:
                    return None
        return None

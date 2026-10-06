import os
from openai import OpenAI
from anthropic import Anthropic
from google import genai

class BaseAIProvider:
    def generate_text(self, prompt: str, system_instruction: str = None) -> str:
        raise NotImplementedError("Each provider must implement generate_text")

class GeminiProvider(BaseAIProvider):
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        
    def generate_text(self, prompt: str, system_instruction: str = None) -> str:
        config = {}
        if system_instruction:
            config["system_instruction"] = system_instruction
        # Use gemini-2.5-flash as default
        response = self.client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=config
        )
        return response.text

class ClaudeProvider(BaseAIProvider):
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)
        
    def generate_text(self, prompt: str, system_instruction: str = None) -> str:
        kwargs = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}]
        }
        if system_instruction:
            kwargs["system"] = system_instruction
        response = self.client.messages.create(**kwargs)
        return response.content[0].text

class OpenAIProvider(BaseAIProvider):
    def __init__(self, api_key: str, base_url: str = None, model: str = "gpt-4o"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        
    def generate_text(self, prompt: str, system_instruction: str = None) -> str:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        return response.choices[0].message.content

class MistralProvider(BaseAIProvider):
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key, base_url="https://api.mistral.ai/v1")
        
    def generate_text(self, prompt: str, system_instruction: str = None) -> str:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model="mistral-large-latest",
            messages=messages
        )
        return response.choices[0].message.content

class QwenProvider(BaseAIProvider):
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        
    def generate_text(self, prompt: str, system_instruction: str = None) -> str:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model="qwen-turbo",
            messages=messages
        )
        return response.choices[0].message.content

class DeepSeekProvider(BaseAIProvider):
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
        
    def generate_text(self, prompt: str, system_instruction: str = None) -> str:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=messages
        )
        return response.choices[0].message.content

class LlamaProvider(BaseAIProvider):
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        
    def generate_text(self, prompt: str, system_instruction: str = None) -> str:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model="llama3-8b-8192",
            messages=messages
        )
        return response.choices[0].message.content

def get_ai_service(provider: str, api_key: str) -> BaseAIProvider:
    provider = provider.lower().strip()
    if provider == "gemini":
        return GeminiProvider(api_key)
    elif provider == "claude":
        return ClaudeProvider(api_key)
    elif provider == "openai":
        return OpenAIProvider(api_key)
    elif provider == "mistral":
        return MistralProvider(api_key)
    elif provider == "qwen":
        return QwenProvider(api_key)
    elif provider == "deepseek":
        return DeepSeekProvider(api_key)
    elif provider == "llama":
        return LlamaProvider(api_key)
    else:
        raise ValueError(f"Unsupported AI provider: {provider}")

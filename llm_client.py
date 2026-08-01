import os

from openai import OpenAI


class LLMClient:
    def __init__(self, base_url=None, model=None):
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5vl:32b")
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=os.getenv("OLLAMA_API_KEY", "ollama"),
        )
        self.conversation_history = []

    def reset_context(self):
        self.conversation_history = []

    def get_chat_response(self, message):
        try:
            self.conversation_history.append({"role": "user", "content": message})
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation_history,
            )
            assistant_message = response.choices[0].message.content or ""
            self.conversation_history.append({"role": "assistant", "content": assistant_message})
            return assistant_message
        except Exception as e:
            return str(e)

    def get_vision_response(self, prompt, image_base64):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                            },
                        ],
                    }
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            return str(e)

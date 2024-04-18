from openai import OpenAI

class ChatGPTClient:
    def __init__(self, api_key):
        self.client = OpenAI(api_key=api_key)
        self.conversation_history = []

    def get_chat_response(self, message):
        try:
            # Append user's message to conversation history
            self.conversation_history.append({"role": "user", "content": message})

            # Make the API call with the updated conversation history
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo-0125",
                messages=self.conversation_history
            )

            # Extract the assistant's message from the response
            assistant_message = response.choices[0].message.content

            # Append assistant's message to conversation history
            self.conversation_history.append({"role": "assistant", "content": assistant_message})

            return assistant_message
        except Exception as e:
            return str(e)


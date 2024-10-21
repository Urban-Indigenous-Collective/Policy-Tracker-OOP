class ChatGPTQuestionnaire:
    def __init__(self, chat_client):
        self.chat_client = chat_client

    def ask_summary(self, text):
        return self.chat_client.get_chat_response(
            f"Please carefully evaluate the following text, and do not respond before analyzing it. \n\n {text} \n\n Please summarize the aforementioned text in 5 sentences or less."
        )

    def ask_mechanisms_eval(self, text):
        response = self.chat_client.get_chat_response(
            f"Can you quote whether the following text includes mechanisms for evaluation? These could include but are not limited to a final report, consultation with community, tribal consultation, a Tribal Crisis Response Plan (TCRP), monitoring, or data collection. Respond with only Yes or No. \n\n {text}"
        )
        return response.strip(".")

    def ask_mechanisms_expl(self, text):
        return self.chat_client.get_chat_response(
            f"Please quote the previously mentioned text where it mentions specific mechanisms for evaluation (a final report, consultation with community, tribal consultation, a Tribal Crisis Response Plan (TCRP), monitoring, or data collection). Create a numbered list of ALL mechanisms. \n\n {text}"
        )

    def ask_gender_inclusive_eval(self, text):
        response = self.chat_client.get_chat_response(
            f"Does the following text use gender-inclusive language? This may include expanding specific terms to refer to a broader range of individuals or simply using gender-neutral language throughout. Reply simply with Yes or No. \n\n {text}"
        )
        return response.strip(".")

    def ask_gender_inclusive_expl(self, text):
        return self.chat_client.get_chat_response(
            f"Please explain why or why not the text uses gender-inclusive language in 3 sentences or less. \n\n {text}"
        )

    def ask_prevention_efforts_eval(self, text):
        response = self.chat_client.get_chat_response(
            f"Please evaluate the following text for any prevention efforts. These might include training or awareness efforts related to specific issues. Respond with Yes or No. \n\n {text}"
        )
        return response.strip(".")

    def ask_prevention_efforts_expl(self, text):
        return self.chat_client.get_chat_response(
            f"Please quote the text if any prevention efforts are identified. If none are found, return 'No.' \n\n {text}"
        )

    def ask_centering_indigenous_voices(self, text, indigenous_sponsors):
        return self.chat_client.get_chat_response(
            f"Please evaluate the level of input from Indigenous politicians and communities in the following text. The Indigenous politicians sponsoring the legislation are: {indigenous_sponsors}. Return either No, Somewhat, or Yes with a 3-sentence explanation. \n\n {text}"
        )

    def ask_survivor_relative_input_eval(self, text):
        response = self.chat_client.get_chat_response(
            f"Evaluate the level of input from survivors or relatives in the following text. Return either No, Somewhat, or Yes. \n\n {text}"
        )
        return response.strip(".")

    def ask_categories_eval(self, text):
        return self.chat_client.get_chat_response(
            f"Evaluate the text and return the most applicable categories: Taskforce, Day of Recognition, US Law Enforcement, Tribal Law Enforcement, Data Collection, MMIP Relatives. \n\n {text}"
        )

    def ask_uic_pros(self, data_points):
        return self.chat_client.get_chat_response(
            f"Using the following data points, please summarize the benefits or pros: \n\n {data_points}"
        )

    def ask_uic_cons(self, data_points):
        return self.chat_client.get_chat_response(
            f"Using the following data points, please summarize the drawbacks or cons: \n\n {data_points}"
        )
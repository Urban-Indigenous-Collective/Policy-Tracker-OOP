class ChatGPTQuestionnaire:
    def __init__(self, chat_client):
        self.chat_client = chat_client

    def ask_summary(self, text):
        return self.chat_client.get_chat_response(
            f"Slow down and take your time. Accuracy is imperative. Please carefully evaluate the following legislation, and do not respond before analyzing it -- this pertains to each question I will ask. \n\n {text} \n\n Please summerize the aformentioned legislation in in 5 sentences or less."
        )

    def ask_mechanisms_eval(self, text):
        response = self.chat_client.get_chat_response(
            f"Do not decide if the text contains prevention efforts before reading the following question, and then carefully evaluating the legislation. Take your time. Can you quote the previously mentioned legislation includes mechanisms for evaluation? These could include but are not limited to a final report, consultation with community, tribal consulation, a Tribal Crisis Response Plan (TCRP), monitoring, or data collection. Do not include training as a mechanism for evaluation. Respond with only Yes or No. \n\n"
        )
        return response.strip(".")

    def ask_mechanisms_expl(self, text):
        return self.chat_client.get_chat_response(
            f"Based on your answer to the previous question, please quote the previously mentioned legislation where it mentions the specific mechanisms for evaluation (a final report, consultation with community, tribal consulation, a Tribal Crisis Response Plan (TCRP), monitoring, or data collection). Create a numbered list of ALL mechanisms of evaluation. Exclude the use of * or ** in your answer. \n\n"
        )

    def ask_gender_inclusive_eval(self, text):
        response = self.chat_client.get_chat_response(
            f"Slow down and take your time. Accuracy is imperative. Do not respond before reading the following question and then reviewing this legislation: \n\n {text} \n\n Does the previously mentioned legislation use gender inclusive language? This may include expanding Missing and Murdered Indigenous Womens crisis to refer to missing Indigenous people in general, or simply using gender neutral language throughout. Reply simply with Yes or No \n\n"
        )
        return response.strip(".")

    def ask_gender_inclusive_expl(self, text):
        return self.chat_client.get_chat_response(
            f"Does the previously mentioned legislation use gender inclusive language? This may include expanding Missing and Murdered Indigenous Womens crisis to refer to missing Indigenous people in general, or simply using gender neutral language throughout. Explain why in 3 sentences or less. Do not restate the original question in your answer. \n\n"
        )

    def ask_prevention_efforts_eval(self, text):
        response = self.chat_client.get_chat_response(
            f"Slow down and take your time. Accuracy is imperative. Do not respond before fully reading the following question and then reviewing this legislation: \n\n {text} \n\n Take your time and be accurate. Please evaluate the previously mentioned legislation for any prevention efforts regarding Missing and Murdered Indigenous Persons, including but not limited to training or awareness efforts. Double check your work before answering. Please answer with just Yes or No \n\n"
        )
        return response.strip(".")

    def ask_prevention_efforts_expl(self, text):
        return self.chat_client.get_chat_response(
            f"Do not respond before reading the question, and then reviewing the legislation closely. Take your time and be accurate. Please evaluate the previously mentioned legislation for any prevention efforts regarding Missing and Murdered Indigenous Persons including but not limited to training or awareness efforts. If any prevention efforts are identified, please quote the text and return the quoted text. If no prevention efforts can be identified, please return \”No\”."
        )

    def ask_centering_indigenous_voices(self, text, indigenous_sponsors):
        return self.chat_client.get_chat_response(
            f"Slow down and take your time. Accuracy is imperative. Do not respond before fully reading the following question and then reviewing this legislation: \n\n {text} \n\n Take your time and be accurate. Please evaluate the previously mentioned legislation for the level of input from MMIP survivors, relatives of MMIP survivors, Indigenous politicians, and Indigenous communities in general in the following legislation. The following Indigenous politicans are sponsoring the legislation: {indigenous_sponsors} \n\n Double check your work before answering. Please return either No, Somewhat, and Yes alongside a 3 sentence (or less) explaination. If no mention is made, return No. \n\n"
        )

    def ask_survivor_relative_input_eval(self, text):
        response = self.chat_client.get_chat_response(
            f"Do not respond before fully reading the following question and then reviewing the previously mentioned legislation. Take your time and be accurate. Please evaluate the previously mentioned legislation for the level of input from MMIP survivors or relatives of MMIP survivors in the following legislation. Please return either No, Somewhat, or Yes. Do not include an explaination. If no mention is made, return No. \n\n"
        )
        return response.strip(".")

    def ask_categories_eval(self, text):
        return self.chat_client.get_chat_response(
            f"Please evaluate the previously mentioned legislation and return the most applicable categories in a comma seperated list: Taskforce, Day of Recognition, US Law Enforcement, Tribal Law Enforcement, Data Collection, MMIP Relatives \n\n"
        )

    def ask_uic_pros(self, data_points):
        return self.chat_client.get_chat_response(
            f"Using the following data points: \n\n {data_points} \n\n please summarize the benefits or pros of the the previously mentioned legislation in a numbered list. Exclude the use of * or ** in your answer."
        )

    def ask_uic_cons(self, data_points):
        return self.chat_client.get_chat_response(
            f"Using the following data points: \n\n {data_points} \n\n please summarize the drawbacks or cons of the previoisly memtioned legislation in a numbered list. Exclude the use of * or ** in your answer. \n\n"
        )
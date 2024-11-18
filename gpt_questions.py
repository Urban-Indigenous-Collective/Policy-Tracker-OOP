class ChatGPTQuestionnaire:
    def __init__(self, chat_client):
        self.chat_client = chat_client

    #Collecting bill details for executive order links
    def ask_state(self, text):
        return self.chat_client.get_chat_response(
            f"Slow down and take your time. Accuracy is imperative. Please carefully evaluate the following legislation, and do not respond before analyzing it -- this pertains to each question I will ask. \n\n {text} \n\n Please identify the state associated with this executive order or DOJ memo. Return the answer ONLY as the capitalized initials (ex: \"CT\", \"NY\", etc). If it’s a federal executive order, return \"National\". If it's a Justice Department press release, double check the entire body text to find the correct state. Return only state initials such as \"CT\" or \"NY\" or the word \"National\" with no explaination."
        )

    def ask_bill_number(self, text):
        return self.chat_client.get_chat_response(
            f"Return the following document's bill number. For DOJ press releases, look for the string \"Press Release Number:\" and get the numbers that follow the colon such ex: \"24-570\" and format it as \"DOJ24-570\". For executive orders find the string \"Executive Order\" and get the numbers that follow it ex:\"14053\" and format the final answer as \"EO14053\". Same instructions for a Presidental Proclaimation, which should be formatted as \"P12345\"  : \n\n {text} \n\n This is a search and return operation. The final answer should include no explaination. If no press release number can be found in the text (which do happen sometimes) return an empty string."
        )


    def ask_title(self, text):
        return self.chat_client.get_chat_response(
            f"Return the following document's title and do not decide on what the title is before verifying your preposed string matches exactly what's in the source text: \n\n {text} \n\n  Be sure to return the exact title which can be long. This is a search and return operation. If you're having trouble finding the title on a Federal Register document, you can find it immediately after the executive order number ex: \"Executive Order 14053 of November 15, 2021\" or \"Proclamation 10752 of May 3, 2024\" (which you should not return in the final title) followed by the title \"Improving Public Safety and Criminal Justice for Native Americans and Addressing the Crisis of Missing or Murdered Indigenous People\".  Return just the full title, which you've verified actually exists, ex: \"Document Title and Name\" with no explaination."
        )

    def ask_chamber(self, text):
        return self.chat_client.get_chat_response(
            f"Which governmental branch or specific department is leading the initiative in the mentioned text? If it's an Executive Order or Proclaimation, return \"Executive\". If it's a proclaimation, return \"Proclaimation\". Otherwise, return a specific department such as \"Department of Justice\" or \"FCC\". Make sure your choice isn't just the organization which might be publishing or archiving the document, such as the Federal Register. If it's a collaboration between 2 departments or more, return a comma seperated list: \n\n {text} \n\n  "
        )

    def ask_chamber_details(self, text):
        return self.chat_client.get_chat_response(
            f"When was this document signed or released? If it's an executive order or proclaimation, return \"[signature date] - [return \"Executive Order\" or \"Proclaimation\"] signed and Enacted\". If it's a press release, especially a DOJ press release, return the \"Immediate release\" string and append the release date to the final return item as such: \"[date] - [Immadite release string (add comma and the office which may exist if its a DOJ press release)]\". If you're having trouble finding the date on a DOJ memo, it's always after \"Press Release\" and the following title.  \n\n {text} \n\n  "
        )

    def ask_session(self, text):
        return self.chat_client.get_chat_response(
            f"Identify which presidential administration is responsible for this initiative ex: \"Trump Administration, 2016 - 2020\" or \"Biden Administration, 2020-2024\" or \"Obama Administration, 2008 - 2016\" \n\n {text} \n\n  "
        )
    
    def ask_sponsors(self, text):
        return self.chat_client.get_chat_response(
            f"Which tribal members, tribal representatives, tribal organizations, carrer civil servants (ex: US attorneys or FBI agents), political appointees, and elected officals are supporting this initiative? When identifying Indigenous sponsors, be sure to be as specific as possible by listing their tribal affiliation if available. If given a general statement, like \"Supported by all 4 Federally recognized nations in Louisiana\", or \"each of the nine federally recognized Tribes in Oregon\" list look up and add each individual tribe to your list. If you can list all the tribes, then you don't need to include a general statement like \"representatives from 10 confederated nations [followed by comma seperated names]\". If listing an individual person who's Indigenous, and you have their specific tribal affiliations, return their entry as \"First Last [Tribe 1, Tribe 2, Tribe 3]\". For non-Indigenous sponsors, include their role similarly in brackets ex: \"First Last [United States Secretary of the Interior]\" Be sure to also include non-Indigenous advocates and Indigenous politicans in your answer if they are mentioned. Return your answer in a comma seperated list, capitalized as appropriate for a title ex: \"Here’s an Example of What Title Caps Should Look Like, See What I Mean?\". Do not include an explaination. \n\n {text} \n\n  "
        )

    def ask_indigenous_sponsors(self, text, sponsors):
        return self.chat_client.get_chat_response(
            f"Of the sponsors mentioned in the previous text"
            "Identify which of these are tribes representing Indian Country. If there is a person's name associated with a tribe, include it with the tribal name. "
            "Return your answer as a comma-separated list formatted as: 'Name [Tribe]' if a name is present, or just '[Tribe]' if no name is associated. "
            "Only include those explicitly mentioned in the text. If no Indigenous sponsors can be identified, return an empty string."
            "Review the following list closely: \n\n{sponsors}\n\n"
        )

    def ask_last_updated(self, text):
        return self.chat_client.get_chat_response(
            f"Return the document's signature or release date in the following format YYYY-MM-DD. Do not return any explaination. \n\n {text} \n\n  "
        )



    #Culturally tailored UIC analysis
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
            f"Do not respond before reading the question, and then reviewing the legislation closely. Take your time and be accurate. Please evaluate the previously mentioned legislation for any prevention efforts regarding Missing and Murdered Indigenous Persons including but not limited to training or awareness efforts. If any prevention efforts are identified, please quote the text and return the quoted text. If there are multiple quotes to return, do so in a numbered list without * or **. If no prevention efforts can be identified, please return \”No\”."
        )

    def ask_centering_indigenous_voices_eval(self, text, indigenous_sponsors):
        response = self.chat_client.get_chat_response(
            f"Slow down and take your time. Accuracy is imperative. Do not respond before fully reading the following question and then reviewing this legislation: \n\n {text} \n\n Take your time and be accurate. Please evaluate the previously mentioned legislation for the level of input from MMIP survivors, relatives of MMIP survivors, Indigenous politicians, and Indigenous communities in general in the following legislation. The following Indigenous politicans are sponsoring the legislation: {indigenous_sponsors} \n\n Double check your work before answering. Please return either No, Somewhat, and Yes. Do not include an explaination. If no mention is made, return No. \n\n"
        )
    
        return response.strip(".")


    def ask_centering_indigenous_voices_expl(self, text, indigenous_sponsors):
        return self.chat_client.get_chat_response(
            f"Slow down and take your time. Accuracy is imperative. Please share a 3 sentence (or less) explaination about the inclusion of how you determined the previously mentioned legislation's level and nature of input from MMIP survivors, relatives of MMIP survivors, Indigenous politicians, and Indigenous communities in general. The following Indigenous politicans are sponsoring the legislation: {indigenous_sponsors} \n\n Double check your work before answering. If no mention is made, return No. \n\n"
        )

    def ask_survivor_relative_input_eval(self, text):
        response = self.chat_client.get_chat_response(
            f"Do not respond before fully reading the following question and then reviewing the previously mentioned legislation. Take your time and be accurate. Please evaluate the previously mentioned legislation for the level of input from MMIP survivors or relatives of MMIP survivors in the following legislation. If you identify any Indigenous organizations mentioned in the legislation, you should use your web access to look up the organization and determine if they focus on supporting MMIP survivors. Do not skip this step. The inclusion of an organization which supports MMIP should trigger a yes answer. Please return either No, Somewhat, or Yes. Do not include an explaination. If no mention is made, return No. \n\n"
        )
        return response.strip(".")
    
    def ask_survivor_relative_input_expl(self, text):
        response = self.chat_client.get_chat_response(
            f"Do not respond before fully reading the following question and then reviewing the previously mentioned legislation. Take your time and be accurate. Please share your explaination for how you determined why the legislation does or does not include input from MMIP survivors or relatives of MMIP survivors in the following legislation. If no mention is made, return No. \n\n"
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
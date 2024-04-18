from wikipedia_api_client import WikipediaAPIClient
from fuzzywuzzy import fuzz
import re


class IndigenousDatabase:

    def __init__(self):
        self.database = []
        self.wikipedia_client = WikipediaAPIClient()

    def build_category_dict(self, database, url, ethnicity):
        #Get all politicians in this category and covert them to a list
        politicians_category = self.wikipedia_client.parse_category_and_subcategories(url)
        for politician in politicians_category:
            politician_dict = {
                "name": politician,
                "party": "N/A",
                "state": "N/A",
                "ethnicity": ethnicity,
                "offices_held": "N/A"
            }
            database.append(politician_dict)

    def build_database(self):
        list_url = "https://en.wikipedia.org/wiki/List_of_Native_American_politicians"
        self.database = self.wikipedia_client.parse_list_page(list_url)

        self.build_category_dict(self.database, "Native_American_state_legislators", "N/A")
        self.build_category_dict(self.database, "21st-century Native American politicians", "N/A")
        self.build_category_dict(self.database, "Native_Hawaiian_politicians", "Native Hawaiian")
        # Manually adjust nickname entries
        self.manual_adjustments()
        print("manual adjustments made")

    def manual_adjustments(self):
        # Find and replace or directly add the entry for Donny Olson
        for i, entry in enumerate(self.database):
            if entry['name'].lower() in ['donny olson', 'donald olson']:
                self.database[i] = {
                    "name": "Donald Olson",
                    "party": "Democratic",
                    "state": "Alaska",
                    "ethnicity": "Iñupiat",
                    "offices_held": "N/A"
                }
                break
        else:
            # If not found, we add it directly
            self.database.append({
                "name": "Donald Olson",
                "party": "Democratic",
                "state": "Alaska",
                "ethnicity": "Iñupiat",
                "offices_held": "N/A"
            })


    def print_database(self):
        print("printing database!")
        for politician in self.database:
            print(politician['name'] + " " + politician['ethnicity'])
    
    def get_all_records(self):
        # Return the list of all records
        self.build_database()
        return self.database


    def parse_name_from_input(self, user_input):
        # Update regex to remove titles with optional periods, and party/state affiliations 
        # including and after them, enclosed in either brackets or parentheses.
        name_part = re.sub(
            r"^(Rep\.?\s|Representative\s|Sen\.?\s|Senator\s|Gov\.?\s|Governor\s)|\s*\[[D|R].*?\]|\s*\([D|R].*?\).*$", 
            "", 
            user_input, 
            flags=re.I
        )
        # Extract the clean name part, ensuring hyphenated last names are preserved
        name_part = name_part.strip()

        # Further normalize by replacing en dashes with hyphens if they're part of the name
        normalized_name_part = self.normalize_hyphens_and_en_dashes(name_part)

        return normalized_name_part


    def normalize_hyphens_and_en_dashes(self, name):
        # Replace en dashes with hyphens in the given name string
        return name.replace('–', '-')

    def is_indigenous_sponsor(self, input_name):
        # Normalize the input name
        parsed_input_name = self.parse_name_from_input(input_name)
        normalized_input_name = self.normalize_hyphens_and_en_dashes(parsed_input_name).lower()

        for db_entry in self.database:
            # Normalize the database entry name
            db_name_for_comparison = self.normalize_hyphens_and_en_dashes(self.parse_name_from_input(db_entry['name'])).lower()
            
            # Use fuzzy matching to compare names
            match_score = fuzz.partial_ratio(normalized_input_name, db_name_for_comparison)
            if match_score > 90:  # You can adjust this threshold as needed
                return True
        return False

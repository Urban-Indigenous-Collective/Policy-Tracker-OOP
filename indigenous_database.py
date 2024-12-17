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
            # If not found, we add Donald Olson directly
            self.database.append(
                {
                    "name": "Donald Olson",
                    "party": "Democratic",
                    "state": "Alaska",
                    "ethnicity": "Iñupiat",
                    "offices_held": "N/A"
                }
            )

        # Add Ingrid Cumberlidge separately
        self.database.append(
            {
                "name": "Ingrid Cumberlidge",
                "party": "N/A",
                "state": "Alaska",
                "ethnicity": "Aleut, Tlingit",
                "offices_held": "MMIP Coordinator (District of Alaska)"
            }
        )

        # Add Ingrid Cumberlidge separately
        self.database.append(
            {
                "name": "Ingrid Goodyear",
                "party": "N/A",
                "state": "Alaska",
                "ethnicity": "Aleut, Tlingit",
                "offices_held": "MMIP Coordinator (Districts of Alaska & Great Plains)"
            }
        )

        # Add MMIP Coordinators separately
        self.database.append(
            {
                "name": "Cedar Wilkie Gillette",
                "party": "N/A",
                "state": "Oregon",
                "ethnicity": "Mandan, Hidatsa, Arikara Nation, Turtle Mountain Band of Chippewa",
                "offices_held": "MMIP Coordinator (Northwest Region), MMIP Coordinator (District of Oregon)"
            }
        )

        # Add MMIP Coordinators separately
        self.database.append(
            {
                "name": "Shaniya Decker",
                "party": "N/A",
                "state": "New Mexico",
                "ethnicity": "Salish, Nakoda, Turtle Mountain Band of Chippewa",
                "offices_held": "MMIP Coordinator (District of New Mexico)"
            }
        )

        # Add MMIP Coordinators separately
        self.database.append(
            {
                "name": "Patti Buhl",
                "party": "N/A",
                "state": "Oklahoma",
                "ethnicity": "Citizen of the Cherokee Nation",
                "offices_held": "MMIP Coordinator (District of Northern Oklahoma)"
            }
        )

        # Add MMIP Coordinators separately
        self.database.append(
            {
                "name": "Bree Black Horse",
                "party": "N/A",
                "state": "Washington",
                "ethnicity": "Seminole Nation of Oklahoma",
                "offices_held": "MMIP Coordinator (District of Eastern Washington)"
            }
        )


        # Add MMIP Coordinators separately
        self.database.append(
            {
                "name": "Allison Morrisette",
                "party": "N/A",
                "state": "South Dakota",
                "ethnicity": "Oglala Lakota",
                "offices_held": "MMIP Coordinator (South Dakota)"
            }
        )


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


    def get_indigenous_sponsor_entry(self, input_name):
        """
        Retrieves the Indigenous sponsor's data from the database based on a robust search logic.
        """
        # Step 1: Clean the input name
        def clean_name(name):
            # Remove any text inside parentheses along with the parentheses
            name = re.sub(r'\(.*?\)', '', name).strip()
            # Remove any text after a dash (if one exists)
            name = name.split('-', 1)[0].strip()
            return name

        parsed_input_name = self.parse_name_from_input(input_name)
        cleaned_input_name = clean_name(parsed_input_name)
        normalized_input_name = self.normalize_hyphens_and_en_dashes(cleaned_input_name).lower()

        print(f"Name of sponsor to be checked in Indigenous DB: {normalized_input_name}")

        # Step 2: Search the database for a robust match
        best_match = None
        highest_score = 0
        threshold = 90  # Adjust this threshold for fuzzy matching tolerance

        for db_entry in self.database:
            # Normalize the database entry name
            db_name = db_entry['name']
            cleaned_db_name = clean_name(self.parse_name_from_input(db_name))
            normalized_db_name = self.normalize_hyphens_and_en_dashes(cleaned_db_name).lower()

            # Perform fuzzy matching
            match_score = fuzz.partial_ratio(normalized_input_name, normalized_db_name)
            
            if match_score > threshold and match_score > highest_score:
                best_match = db_entry
                highest_score = match_score

        # Step 3: Return the matched entry with debug logs
        if best_match:
            print(f"Best Indigenous data match found: {best_match} (Score: {highest_score})")
            return best_match
        else:
            print("No match found in Indigenous DB.")
            return None
import datetime

class LegiScanProcessor:

    def __init__(self, indigenous_db):
        self.indigenous_db = indigenous_db
        self.status_codes = {
            0: "Pre-filed or pre-introduction",
            1: "Introduced",
            2: "Engrossed",
            3: "Enrolled",
            4: "Passed",
            5: "Vetoed",
            6: "Failed Limited support based on state",
            7: "Override Progress",
            8: "Chaptered Progress",
            9: "Refer Progress",
            10: "Report Pass Progress",
            11: "Report DNP Progress",
            12: "Draft Progress"
        }
        self.chamber_full_names = {
            'A': 'House',  # Assembly is standardized to House
            'S': 'Senate',
            'H': 'House',  # Handle 'H' as House
            'L': 'Legislative Body',  # Potentially for unicameral legislature
            'N/A': 'Not Available'  # Handle cases where chamber info is missing
        }

    def identify_indigenous_sponsors(self, sponsors):
        """
        Identifies and returns a list of Indigenous sponsors from the given list of sponsors.
        """
        sponsors = [name.strip() for name in sponsors.split(',')]
        indigenous_sponsors = []

        for sponsor in sponsors:
            if self.indigenous_db.is_indigenous_sponsor(sponsor):
                indigenous_sponsors.append(sponsor)

        return indigenous_sponsors

    def check_bill_status(self, bill_details):
        """
        Checks the status of a bill.
        """
        if bill_details['bill']['completed'] == 1:
            return "Passed"
        else:
            today = datetime.date.today()
            session_end_year = bill_details['bill']['session']['year_end']
            session_end_date = datetime.date(session_end_year, 12, 31)

            if today > session_end_date:
                return "Failed"
            else:
                return "Pending"

    def get_chamber_details(self, bill):
        """
        Extracts the chamber details (full name of the chamber) from a bill.
        """
        current_body_short = bill.get('body', 'N/A')
        chamber = self.chamber_full_names.get(current_body_short, 'Unknown')
        return chamber

    def get_latest_action(self, bill):
        """
        Extracts the latest action details from a bill.
        """
        history = bill.get('history', [])
        if history:
            latest_action = history[-1]  # Get the most recent action
            action_text = latest_action.get('action', 'N/A')
            action_chamber = latest_action.get('chamber', 'N/A')
            action_date = latest_action.get('date', 'N/A')
            chamber_details = f"{action_date} - {action_chamber}: {action_text}"
        else:
            chamber_details = 'N/A'
        
        return chamber_details

    def get_bill_link(self, bill):
        """
        Extracts the URL link of the bill.
        """
        return bill.get('url', 'N/A')
import datetime

class LegiScanProcessor:
    
    def __init__(self, indigenous_db):
        self.indigenous_db = indigenous_db

    def identify_indigenous_sponsors(self, sponsors):
        """
        Identifies and returns a list of Indigenous sponsors from the given list of sponsors.
        """
        sponsors = [name.strip() for name in sponsors.split(',')]
        indigenous_sponsors = []

        for sponsor in sponsors:
            print(sponsor)
            print(self.indigenous_db.is_indigenous_sponsor(sponsor))
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
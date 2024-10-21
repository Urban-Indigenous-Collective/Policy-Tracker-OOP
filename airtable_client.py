from pyairtable import Table

class AirtableClient:
    def __init__(self):
        # Initialize the Airtable connection with provided values
        api_key='REDACTED_AIRTABLE_PAT.',
        base_id='app0nHzjgm8HEKOCQ',
        table_name='Main v3'
        
        self.table = Table(api_key, base_id, table_name)

    def check_url_in_airtable(self, url):
        # Search for the URL in the Airtable table
        formula = f"{{URL}} = '{url}'"
        records = self.table.all(formula=formula)
        
        if records:
            # Return True if a record is found, along with its data
            return True, records[0]['fields']
        else:
            # Return False if no record is found
            return False, None
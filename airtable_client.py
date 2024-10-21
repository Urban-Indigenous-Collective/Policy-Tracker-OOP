from pyairtable import Table

class AirtableClient:
    def __init__(self):
        # Initialize the Airtable connection with provided values
        api_key='pat474Sk4etSoE1UO.96adc928e0d0082dc93459b20617ec93ed914124541a7e7d28f36996a18863a4'
        base_id='app0nHzjgm8HEKOCQ'
        table_name='Main v3'
        
        self.table = Table(api_key, base_id, table_name)

    def check_url_in_airtable(self, url):
        # Search for the URL in the Airtable table
        formula = f"{{Bill Text}} = '{url}'"
        records = self.table.all(formula=formula)
        
        if records:
            # Return True if a record is found, along with its data
            return True, records[0]['fields']
        else:
            # Return False if no record is found
            return False, None
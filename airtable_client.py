import os

from pyairtable import Table


class AirtableClient:
    def __init__(self):
        api_key = os.getenv('AIRTABLE_API_KEY')
        base_id = os.getenv('AIRTABLE_BASE_ID')
        table_name = os.getenv('AIRTABLE_TABLE', 'Main v3')

        if not api_key or not base_id:
            raise ValueError('AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set')

        self.table = Table(api_key, base_id, table_name)

    def check_url_in_airtable(self, url, category):
        formula = f"{{{category}}} = '{url}'"
        records = self.table.all(formula=formula)

        if records:
            return True, records[0]['fields']
        return False, None

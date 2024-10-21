from pyairtable import Table

# Initialize Airtable connection
def check_url_in_airtable(api_key, base_id, table_name, url):
    table = Table(api_key, base_id, table_name)
    
    # Search for the URL in the Airtable table
    records = table.all(formula=f"{{URL}} = '{url}'")
    if records:
        return True, records[0]['fields']  # Return true and record details if found
    else:
        return False, None  # Return false if not found
import requests


class APIClient:
    def __init__(self, api_key):
        self.api_key = api_key

    def _make_request(self, endpoint, params):
        url = f'https://api.legiscan.com/?key={self.api_key}&op={endpoint}'
        print(f'Legiscan request URL: {url}')
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            return None

    def get_api_key(self):
        return self.api_key

    def get_bill_text(self, bill_id):
        data = self._make_request('getBillText', {'id': bill_id})
        return data['text'] if data and 'text' in data else None

    def get_bill_details(self, bill_id):
        if not bill_id:
            return "Invalid Bill ID"

        url = f'https://api.legiscan.com/?key={self.api_key}&op=getBill&id={bill_id}'
        print("Printing from inside Legiscan API call" + url)
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            return "Error fetching bill details from LegiScan API"
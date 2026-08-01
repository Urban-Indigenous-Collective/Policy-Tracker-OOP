import requests
from bs4 import BeautifulSoup
import re

class WikipediaAPIClient:
    def __init__(self):
        self.base_url = "https://en.wikipedia.org/w/api.php"
        self.session = requests.Session()

    def get_page_content(self, url):
        response = self.session.get(url)
        return response.content



    def parse_municipal_offices(self, url):
        content = self.get_page_content(url)
        soup = BeautifulSoup(content, 'html.parser')

        politicians = []
        current_state = "Unknown"

        municipal_heading_tag = soup.find('h2', id='Municipal_offices')
        if municipal_heading_tag is None:
            return politicians

        municipal_heading = municipal_heading_tag.parent
        for element in municipal_heading.find_next_siblings():
            if element.name == 'h3':
                current_state = element.find('span', class_='mw-headline').get_text(strip=True)
            elif element.name == 'ul':
                for li in element.find_all('li'):
                    text = li.get_text(strip=True)
                    text = re.sub(r'\[\d+\]', '', text)  # Remove reference numbers

                    # Extract only the name (first part before a comma or parenthesis)
                    name_match = re.match(r'([^,(\[]+)', text)
                    name = name_match.group(1).strip() if name_match else "Unknown"

                    # The rest of the text is treated as offices held
                    offices_held = text.replace(name, '').strip()

                    formatted_entry = f"{name} [N/A-{current_state}] - N/A: {offices_held}"
                    politicians.append(formatted_entry)

                
        return politicians







    def parse_list_page(self, url):
        content = self.get_page_content(url)
        soup = BeautifulSoup(content, 'html.parser')

        politicians_data = []
        current_state = "Unknown"

        # Process Federal and State Offices
        for element in soup.find_all(['div', 'table']):
            if element.name == 'div' and 'mw-heading' in element.get('class', []):
                state_headline = element.find('h3')
                if state_headline:
                    current_state = state_headline.get_text(strip=True)

            elif element.name == 'table' and 'wikitable' in element.get('class', []):
                rows = element.find_all('tr')
                for row in rows[1:]:
                    cols = row.find_all('td')
                    if len(cols) >= 6:
                        name = cols[0].get_text(strip=True)
                        party = cols[4].get_text(strip=True)
                        ethnicity = cols[3].get_text(strip=True)
                        offices_held = re.sub(r'(?<=[a-zA-Z])(?=[A-Z])', ' ', cols[5].get_text(strip=True))

                        politician_dict = {
                            "name": name,
                            "party": party,
                            "state": current_state,
                            "ethnicity": ethnicity,
                            "offices_held": offices_held
                        }
                        politicians_data.append(politician_dict)

        # Process Municipal Offices
        municipal_politicians = self.parse_municipal_offices(url)
        for politician in municipal_politicians:
            # Split the string to create a dictionary
            name, rest = politician.split(" [N/A-")
            state, offices_held = rest.split("] - N/A: ")

            politician_dict = {
                "name": name,
                "party": "N/A",
                "state": state,
                "ethnicity": "N/A",
                "offices_held": offices_held
            }
            politicians_data.append(politician_dict)

        return politicians_data


    def parse_category_page(self, url):
        content = self.get_page_content(url)
        soup = BeautifulSoup(content, 'html.parser')
        # Find all links to politician pages - adjust the selector based on the actual HTML structure
        links = soup.select('.mw-category a')
        politicians = []
        for link in links:
            page_url = "https://en.wikipedia.org" + link.get('href')
            page_content = self.get_page_content(page_url)
            page_soup = BeautifulSoup(page_content, 'html.parser')
            # Extract the desired information from each politician's page
            name = page_soup.select_one('h1').get_text()
            # Further processing for more details
            politicians.append(name)
        return politicians

    def get_category_content(self, category_title):
            params = {
                "action": "query",
                "format": "json",
                "list": "categorymembers",
                "cmtitle": f"Category:{category_title}",
                "cmlimit": "max"
            }
            response = self.session.get(self.base_url, params=params)
            if response.status_code == 200:
                return response.json()
            else:
                return None


    def extract_pages_and_subcategories(self, category_members):
        pages = set()
        subcategories = []

        for member in category_members:
            title = member['title']
            if title.startswith("Category:"):
                subcategory = title.replace("Category:", "")
                subcategories.append(subcategory)
            else:
                pages.add(title)

        return pages, subcategories



    def parse_category_and_subcategories(self, category_title, accumulated_pages=None):
        if accumulated_pages is None:
            accumulated_pages = set()

        # Fetch the content for the current category
        category_content = self.get_category_content(category_title)
        if category_content:
            # Extract pages and subcategories from the current category
            pages, subcategories = self.extract_pages_and_subcategories(category_content['query']['categorymembers'])

            # Add extracted pages to the accumulated set
            accumulated_pages.update(pages)

            # Recursively process each subcategory
            for subcat in subcategories:
                self.parse_category_and_subcategories(subcat, accumulated_pages)

        return accumulated_pages
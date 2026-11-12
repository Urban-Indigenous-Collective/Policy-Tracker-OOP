"""gov_processor analysis fetch must send a browser User-Agent."""

from unittest.mock import MagicMock, patch

from discovery.fetchers import BROWSER_UA
from gov_processor import GovProcessor


def test_get_gov_document_text_sends_browser_ua():
    doc = MagicMock()
    doc.strip_html_tags.return_value = "hello mmip text"
    processor = GovProcessor(doc, indigenous_db=MagicMock())
    processor.federal_register_api = MagicMock()
    processor.federal_register_api.is_federal_register_url.return_value = False

    response = MagicMock()
    response.status_code = 200
    response.headers = {"Content-Type": "text/html"}
    response.content = b"<html><body>hello mmip text</body></html>"

    with patch("gov_processor.requests.get", return_value=response) as get:
        text, err = processor.get_gov_document_text(
            "https://www.michigan.gov/ag/initiatives/mmip"
        )

    assert err is None
    assert text == "hello mmip text"
    get.assert_called_once()
    _, kwargs = get.call_args
    assert kwargs["headers"]["User-Agent"] == BROWSER_UA
    assert kwargs.get("timeout") == 60

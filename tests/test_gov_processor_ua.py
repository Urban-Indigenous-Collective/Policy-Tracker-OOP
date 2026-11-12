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


def test_justice_gov_uses_browser_gated_fetch_not_plain_requests():
    doc = MagicMock()
    processor = GovProcessor(doc, indigenous_db=MagicMock())
    processor.federal_register_api = MagicMock()
    processor.federal_register_api.is_federal_register_url.return_value = False

    body = b"<html><body>U.S. Attorney and FBI Announce Missing and Murdered Indigenous Persons Initiative</body></html>"
    with patch("gov_processor.requests.get") as get, patch(
        "gov_processor.fetch_justice_gov_content",
        return_value=(body, "hash", "text/html"),
    ) as fetch, patch(
        "gov_processor.extract_document_text",
        return_value="U.S. Attorney and FBI Announce Missing and Murdered Indigenous Persons Initiative",
    ):
        text, err = processor.get_gov_document_text(
            "https://www.justice.gov/usao-ak/pr/us-attorney-and-fbi-announce-missing-and-murdered-indigenous-persons-initiative"
        )

    assert err is None
    assert "Missing and Murdered" in text
    fetch.assert_called_once()
    get.assert_not_called()

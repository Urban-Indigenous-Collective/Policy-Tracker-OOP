import io
import base64
import PyPDF2
from bs4 import BeautifulSoup


class DocumentProcessor:

    @staticmethod
    def decode_base64(data, encoding='utf-8'):
        decoded_bytes = base64.b64decode(data)
        try:
            decoded_data = decoded_bytes.decode(encoding)
        except UnicodeDecodeError:
            try:
                decoded_data = decoded_bytes.decode('latin-1')
            except UnicodeDecodeError:
                raise ValueError("Base64 data could not be decoded with utf-8 or latin-1 encoding.")

        # Check if decoded data is actually bytes-like
        if isinstance(decoded_bytes, str):
            raise TypeError("Decoded data is a string, expected a bytes-like object.")

        return base64.b64decode(data)


    def extract_text_from_pdf(self, pdf_data):
        pdf_stream = io.BytesIO(pdf_data)
        pdf_reader = PyPDF2.PdfReader(pdf_stream)
        decoded_text = ""
        for page in pdf_reader.pages:
            text = page.extract_text()
            if text:
                decoded_text += text + "\n"
        return decoded_text

    def strip_html_tags(self, html_content):
        """
        Utility function to strip HTML tags from text.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        return soup.get_text()
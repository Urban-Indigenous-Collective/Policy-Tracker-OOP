import io
from io import BytesIO
import base64
import pypdf
from bs4 import BeautifulSoup
from pdf2image import convert_from_bytes


class DocumentProcessor:
    def __init__(self, llm_provider=None):
        self.llm_provider = llm_provider

    def _get_provider(self):
        if self.llm_provider is None:
            from llm.factory import get_llm_provider
            return get_llm_provider()
        return self.llm_provider

    @staticmethod
    def decode_base64(data, encoding="utf-8"):
        decoded_bytes = base64.b64decode(data)
        try:
            decoded_bytes.decode(encoding)
        except UnicodeDecodeError:
            try:
                decoded_bytes.decode("latin-1")
            except UnicodeDecodeError:
                raise ValueError("Base64 data could not be decoded with utf-8 or latin-1 encoding.")
        if isinstance(decoded_bytes, str):
            raise TypeError("Decoded data is a string, expected a bytes-like object.")
        return base64.b64decode(data)

    def extract_text_from_pdf(self, pdf_data):
        llm = self._get_provider()
        try:
            pdf_stream = io.BytesIO(pdf_data)
            pdf_reader = pypdf.PdfReader(pdf_stream)
            decoded_text = ""
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    decoded_text += text + "\n"
            if decoded_text.strip():
                return decoded_text
            print("No selectable text found in PDF. Falling back to vision OCR...")
            return self.extract_text_with_vision(pdf_data, llm)
        except Exception as e:
            print(f"Error during text extraction: {e}. Falling back to vision OCR...")
            return self.extract_text_with_vision(pdf_data, llm)

    def strip_html_tags(self, html_content):
        soup = BeautifulSoup(html_content, "html.parser")
        return soup.get_text()

    @staticmethod
    def convert_pdf_to_images(pdf_data):
        return convert_from_bytes(pdf_data)

    @staticmethod
    def encode_images_to_base64(images):
        encoded_images = []
        for image in images:
            buffer = BytesIO()
            image.save(buffer, format="JPEG")
            encoded_images.append(base64.b64encode(buffer.getvalue()).decode("utf-8"))
        return encoded_images

    def extract_text_with_vision(self, pdf_data, llm_provider):
        try:
            images = self.convert_pdf_to_images(pdf_data)
            encoded_images = self.encode_images_to_base64(images)
            extracted_text = ""
            for page_num, img_data in enumerate(encoded_images, start=1):
                prompt = (
                    f"You are an OCR tool. Extract all text from this document page (page {page_num}). "
                    "Return only the extracted text with no commentary."
                )
                response = llm_provider.complete_vision(prompt, img_data)
                extracted_text += f"Page {page_num}:\n{response}\n\n"
            return extracted_text
        except Exception as e:
            return f"Error during OCR processing: {e}"

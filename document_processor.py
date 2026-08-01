import io
from io import BytesIO
import os
import base64
import pypdf
from bs4 import BeautifulSoup
from pdf2image import convert_from_bytes
from chatgpt_client import ChatGPTClient

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
        """
        Attempt to extract text from the PDF. If text extraction fails (e.g., image-based PDF),
        fallback to GPT-based OCR using the provided ChatGPT client.
        
        :param pdf_data: Byte data of the PDF.
        :param chatgpt_client: Instance of ChatGPTClient to handle OCR fallback.
        :return: Extracted text as a string.
        """
        try:
            # Attempt to extract text using PyPDF2
            pdf_stream = io.BytesIO(pdf_data)
            pdf_reader = pypdf.PdfReader(pdf_stream)
            decoded_text = ""

            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    decoded_text += text + "\n"

            # If text was successfully extracted, return it
            if decoded_text.strip():
                return decoded_text

            # Log and fallback to GPT OCR
            print("No selectable text found in PDF. Falling back to GPT OCR...")
            chatgpt_client = ChatGPTClient((os.getenv("OPENAI_API_KEY")))
            return self.extract_text_with_gpt(pdf_data, chatgpt_client)

        except Exception as e:
            # Handle exceptions (e.g., PyPDF2 errors) and fallback to GPT OCR
            print(f"Error during text extraction: {e}. Falling back to GPT OCR...")
            return self.extract_text_with_gpt(pdf_data, chatgpt_client)

    def strip_html_tags(self, html_content):
        """
        Utility function to strip HTML tags from text.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        return soup.get_text()

    @staticmethod
    def convert_pdf_to_images(pdf_data):
        images = convert_from_bytes(pdf_data)
        return images

    @staticmethod
    def encode_images_to_base64(images):
        encoded_images = []
        for image in images:
            buffer = BytesIO()
            image.save(buffer, format="JPEG")
            encoded_images.append(base64.b64encode(buffer.getvalue()).decode('utf-8'))
        return encoded_images

    def extract_text_with_gpt(self, pdf_data, chatgpt_client):
        """
        Extract text from image-based PDFs using ChatGPT for OCR.
        
        :param pdf_data: Byte data of the PDF.
        :param chatgpt_client: Instance of ChatGPTClient to handle API requests.
        :return: Extracted text as a string.
        """
        try:
            # Convert PDF to images
            images = self.convert_pdf_to_images(pdf_data)

            # Encode images to base64
            encoded_images = self.encode_images_to_base64(images)

            extracted_text = ""
            for page_num, img_data in enumerate(encoded_images, start=1):
                # Send image data to ChatGPT for OCR
                message = (
                    f"You are an OCR tool. Extract text from the following image (page {page_num}). "
                    f"The image is base64-encoded: {img_data}"
                )
                response = chatgpt_client.get_chat_response(message)
                extracted_text += f"Page {page_num}:\n{response}\n\n"

            return extracted_text
        except Exception as e:
            return f"Error during OCR processing: {e}"
import pandas as pd
import os

class ReportGenerator:
    @staticmethod
    def export_to_excel(bill_data, filename='bill_details.xlsx'):
        # Ensure bill_data is treated as a list of rows
        df = pd.DataFrame(bill_data)  # This works if bill_data is a list of dictionaries

        # Check if the file exists. If it does, read it and append new data.
        if os.path.exists(filename):
            existing_df = pd.read_excel(filename)
            df = pd.concat([existing_df, df], ignore_index=True)

        df.to_excel(filename, index=False)
        print(f"Data exported to {filename}")
        
        # Return the path to the generated Excel file
        return os.path.abspath(filename)

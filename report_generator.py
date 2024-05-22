import pandas as pd
import os

class ReportGenerator:
    @staticmethod
    def export_to_excel(data, filename='bill_details.xlsx'):
        # Convert the list of dictionaries to a DataFrame
        df = pd.DataFrame(data)

        # Ensure 'State' and 'Title' columns exist and replace NaNs with default values
        if 'State' not in df.columns:
            df['State'] = 'No State Info'  # Add column if not exist
        if 'Title' not in df.columns:
            df['Title'] = 'No Title Info'  # Add column if not exist

        # Replace NaN values in 'State' and 'Title' with default values if they exist
        df['State'] = df['State'].fillna('No State Info')
        df['Title'] = df['Title'].fillna('No Title Info')

        # Check for 'error' and 'url' in the DataFrame and modify 'State' and 'Title' accordingly
        if 'error' in df.columns and 'url' in df.columns:
            # Update 'State' column by appending error messages where available
            df['State'] = df.apply(lambda row: f"{row['State']} - Error: {row['error']}" if pd.notna(row['error']) else row['State'], axis=1)
            # Update 'Title' column by appending URL where available
            df['Title'] = df.apply(lambda row: f"{row['Title']} - URL: {row['url']}" if pd.notna(row['url']) else row['Title'], axis=1)
            # Drop the 'error' and 'url' columns as they are no longer needed after merging
            df.drop(['error', 'url'], axis=1, inplace=True)

        # Export the DataFrame to an Excel file, overwriting any existing file
        df.to_excel(filename, index=False)
        print(f"Data exported to {filename}")
        return os.path.abspath(filename)



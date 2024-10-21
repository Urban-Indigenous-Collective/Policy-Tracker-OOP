from flask import Flask, request, send_from_directory, jsonify, render_template
import os
from main_application import MainApplication

app = Flask(__name__)

# Initialize MainApplication
# Assuming MainApplication initializes API clients with hardcoded keys

# Initialize OpenAI and AirTable
legiscan_key = '4bbc7257ba2bbf01b636af5b19cc2212'
openai_key = 'sk-proj-Vr6atYpHcM0kmWmAAD7QT3BlbkFJzFrOANKloNoUfTPaf3ya'


# Pass Airtable table and keys to MainApplication
main_app = MainApplication(legiscan_key, openai_key)


@app.route('/')
def home():
    return render_template('index.html')  # Assuming you have an index.html template

@app.route('/process', methods=['POST'])
def process():
    global process_status
    process_status = "Processing..."
    
    urls_string = request.form['links']
    
    excel_file_path = main_app.process_urls_for_web(urls_string)

    process_status = "Complete"
    if excel_file_path:
        # Construct a URL for the file
        file_url = '/download?path=' + excel_file_path
        return jsonify({'status': 'Complete', 'file_url': file_url})
    else:
        process_status = "Failed"
        return jsonify({'status': 'Failed', 'message': 'No valid data to generate report.'})

@app.route('/download')
def download_file():
    file_path = request.args.get('path')
    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    return send_from_directory(os.path.dirname(file_path), 'bill_details.xlsx', as_attachment=True)


@app.route('/status')
def status():
    progress = main_app.get_progress()
    return jsonify({"status": process_status,
                    "progress": progress})

@app.route('/progress')
def get_progress():
    # Retrieve the current progress from the MainApplication instance
    progress = main_app.get_progress()  # Ensure you have main_app instance available
    # Return the progress as JSON
    return jsonify({"progress": progress})

@app.route('/politician-lookup')
def politician_lookup():
    return render_template('politician_lookup.html')

@app.route('/politician_lookup', methods=['POST'])
def handle_politician_lookup():
    # Extract the list of politician names from the form data
    politicians = request.form.get('politicians', '').split(',')
    politicians = [name.strip() for name in politicians if name.strip()]  # Clean up input
    
    # Use MainApplication to check the Indigenous status of the politicians
    results = main_app.check_politician_indigenous_status(politicians)
    
    # Separate the results into Indigenous and non-Indigenous lists
    indigenous_politicians = [politician for politician, is_indigenous in results.items() if is_indigenous]
    non_indigenous_politicians = [politician for politician, is_indigenous in results.items() if not is_indigenous]
    
    # Format the results into comma-separated lists to send back
    indigenous_list = ', '.join(indigenous_politicians)
    non_indigenous_list = ', '.join(non_indigenous_politicians)
    
    # Format the final HTML response
    results_html = f"<p>Indigenous Politicians: {indigenous_list}</p>"
    results_html += f"<p>Non-Indigenous Politicians: {non_indigenous_list}</p>"
    
    return results_html

@app.route('/fetch_all_indigenous', methods=['GET'])
def fetch_all_indigenous():
    # Assuming main_app has access to indigenous_db which has a method to get all records
    indigenous_politicians = main_app.indigenous_db.get_all_records()
    
    # Format the response
    response_html = "<ul>"
    for politician in indigenous_politicians:
        name = politician.get('name', 'No Name Provided')
        ethnicity = politician.get('ethnicity', 'Ethnicity Not Provided')
        response_html += f"<li>{name} - {ethnicity}</li>"
    response_html += "</ul>"
    
    return response_html


if __name__ == '__main__':
    app.run(debug=True)

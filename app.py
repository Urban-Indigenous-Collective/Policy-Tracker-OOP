from flask import Flask, request, send_from_directory, jsonify, render_template, redirect
import logging
import os
import threading
from dotenv import load_dotenv
from flask_cors import CORS
from main_application import MainApplication
from processing_log import reset as plog_reset, snapshot as plog_snapshot

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


app = Flask(__name__)
CORS(app)

process_status = "Idle"
process_result = {"file_url": None, "message": None}
process_lock = threading.Lock()

# Initialize MainApplication
# Assuming MainApplication initializes API clients with hardcoded keys
load_dotenv()


legiscan_key = os.getenv("LEGISCAN_KEY")
main_app = MainApplication(legiscan_key)

@app.route("/")
def home():
    return redirect('/analyzer')

@app.route('/analyzer')
def analyzer():
    return render_template('index.html')  # Assuming you have an index.html template

@app.route('/health-check')
def health_check():
    # Optionally, perform additional readiness checks here.
    return jsonify({"status": "ok"}), 200

def _run_processing(urls_string):
    global process_status, process_result
    try:
        plog_reset()
        main_app.progress = 0
        excel_file_path = main_app.process_urls_for_web(urls_string)
        if excel_file_path:
            process_result = {
                "file_url": "/download?path=" + excel_file_path,
                "message": None,
            }
            process_status = "Complete"
        else:
            process_result = {
                "file_url": None,
                "message": "No valid data to generate report.",
            }
            process_status = "Failed"
    except Exception as e:
        process_result = {"file_url": None, "message": str(e)}
        process_status = "Failed"


@app.route('/process', methods=['POST'])
def process():
    global process_status, process_result

    with process_lock:
        if process_status == "Processing...":
            return jsonify({"status": "Processing...", "message": "Already processing."}), 409

        urls_string = request.form["links"]
        process_status = "Processing..."
        process_result = {"file_url": None, "message": None}
        thread = threading.Thread(target=_run_processing, args=(urls_string,), daemon=True)
        thread.start()

    return jsonify({"status": "Processing...", "message": "Processing started."}), 202

@app.route('/download')
def download_file():
    file_path = request.args.get('path')
    if not file_path or not os.path.isfile(file_path):
        return jsonify({'error': 'File not found'}), 404
    directory = os.path.dirname(file_path) or '.'
    filename = os.path.basename(file_path)
    return send_from_directory(directory, filename, as_attachment=True)


@app.route('/status')
def status():
    progress = main_app.get_progress()
    detail = main_app.get_status_detail()
    log_snapshot = plog_snapshot()
    response = {
        "status": process_status,
        "progress": progress,
        "phase": detail.get("phase", log_snapshot.get("phase")),
        "phase_label": log_snapshot.get("phase_label", ""),
        "detail": detail.get("detail", log_snapshot.get("detail", "")),
        "log": log_snapshot.get("lines", []),
    }
    if process_status == "Complete" and process_result.get("file_url"):
        response["file_url"] = process_result["file_url"]
    if process_status == "Failed" and process_result.get("message"):
        response["message"] = process_result["message"]
    return jsonify(response)

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
    debug = os.getenv('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    app.run(debug=debug)

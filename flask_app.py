import os
import json
import logging
from flask import Flask, request, jsonify, render_template  # Add render_template
from flask_cors import CORS
from pymongo import MongoClient
from bson.json_util import dumps
from dotenv import load_dotenv
from ruleBased import generate_mongo_query # Import the function from rulebased.py
from urllib.parse import quote_plus

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
dotenv_path = os.path.join(os.getcwd(), ".env")  # Ensure correct path
load_dotenv(dotenv_path)

USERNAME = quote_plus(os.getenv("MONGO_USER", "default_user"))
PASSWORD = quote_plus(os.getenv("MONGO_PASS", "default_pass"))
CLUSTER = os.getenv("MONGO_CLUSTER", "cluster0")

uri = f"mongodb+srv://{USERNAME}:{PASSWORD}@{CLUSTER}.stgq1pn.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
#print(uri)
client = MongoClient(uri)
# MongoDB client setup
db = client["crm_system"]  
collection = db["call_logs"] 
app = Flask(__name__)
# Enable CORS for all routes
CORS(app)  # This will enable CORS for all routes and origins

# Function to handle the natural language query
@app.route('/query', methods=['POST'])
def process_query():
    """
    Handles natural language queries and converts them to MongoDB queries.
    """
    try:
        data = request.get_json()
        if not data or 'query' not in data:
            return jsonify({"error": "Missing 'query' parameter"}), 400

        natural_language_query = data['query']
        logging.info(f"Received Query: {natural_language_query}")

        # Generate MongoDB query using ruleBased.py
        mongo_query = generate_mongo_query(natural_language_query)
        logging.info(f"Generated MongoDB Query: {mongo_query}")

        try:
            mongo_query = json.loads(mongo_query)  # Convert JSON string to Python dict/list
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON format from query generator"}), 400

        # Determine query type and execute
        if isinstance(mongo_query, dict) and "find" in mongo_query:
            results = collection.find(mongo_query["find"])
            result_data = list(results)
            logging.info(f"Find Query Results: {len(result_data)} records found")

        elif isinstance(mongo_query, list):  # Aggregation query
            results = collection.aggregate(mongo_query)
            result_data = list(results)
            logging.info(f"Aggregation Results: {len(result_data)} records found")

        else:
            return jsonify({"error": "Could not parse the query into MongoDB format"}), 400

        if not result_data:
            return jsonify({"message": "No results found"}), 404

        return jsonify(json.loads(dumps(result_data))), 200

    except Exception as e:
        logging.error(f"Error processing query: {e}")
        return jsonify({"error": "An internal server error occurred"}), 500


if __name__ == '__main__':
    port = int(os.getenv("PORT", 4000))  # Use the PORT environment variable if available
    app.run(host='0.0.0.0', port=port, debug=True)

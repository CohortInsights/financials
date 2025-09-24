import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Get connection string
mongo_uri = os.getenv("MONGO_URI")

# Connect to MongoDB
client = MongoClient(mongo_uri)
db = client.get_default_database()  # defaults to "financials"

# Example collection
test = db["test"]


# Quick test: insert and read back
def test_db():
    test_doc = {"status": "ok"}
    result = test.insert_one(test_doc)
    print("Inserted ID:", result.inserted_id)

    doc = test.find_one({"_id": result.inserted_id})
    print("Fetched doc:", doc)

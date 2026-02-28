import time
from twelvelabs import TwelveLabs
import requests
import os
from dotenv import load_dotenv

load_dotenv()

TL_API_KEY = os.environ.get('TL_API_KEY')
if not TL_API_KEY:
    raise RuntimeError("TL_API_KEY environment variable is not set; export it or source your .env file")

url = "https://api.twelvelabs.io/v1.3/indexes/69a24da4765e515a4f6b1b5f"
headers = {"x-api-key": TL_API_KEY}

client = TwelveLabs(api_key=TL_API_KEY)
response = requests.get(url, headers=headers)
index_data = response.json()

index_id = index_data.get('_id')


def add_video(video_name, query):
    """Upload a video to the index, wait for indexing, and search for a query in it"""
    # Construct the full filepath from the default path
    filepath = f"../resources/{video_name}"
    
    # Upload the asset
    with open(filepath, "rb") as video_file:
        asset = client.assets.create(
            method="direct",
            file=video_file
        )
    
    # Create indexed asset
    indexed_asset = client.indexes.indexed_assets.create(
        index_id=index_id,
        asset_id=asset.id,
    )
    print(f"Created indexed asset: id={indexed_asset.id}")
    print(f"Created asset: id={asset.id}")
    
    # Wait for indexing to complete
    print("Waiting for indexing to complete.")
    while True:
        indexed_asset = client.indexes.indexed_assets.retrieve(
            index_id=index_id,
            indexed_asset_id=indexed_asset.id
        )
        if indexed_asset.status == "ready":
            print("Indexing complete!")
            break
        elif indexed_asset.status == "failed":
            raise RuntimeError("Indexing failed")
        else:
            print("Currently indexing...")
            time.sleep(5)
    
    # Analyze the video with the query
    print(f"\nAnalyzing: '{query}'")
    text_stream = client.analyze_stream(
        video_id=indexed_asset.id,
        prompt=query
    )
    
    # Process the results
    analysis_text = ""
    for text in text_stream:
        if text.event_type == "text_generation":
            print(text.text, end="", flush=True)
            analysis_text += text.text
    
    print()  # New line after streaming
    return indexed_asset.id, analysis_text


def delete_video(indexed_asset_id):
    """Remove a video from the index"""
    client.indexes.indexed_assets.delete(
        index_id=index_id,
        indexed_asset_id=indexed_asset_id
    )
    print(f"Deleted video: {indexed_asset_id}")



asset_id, results = add_video("Demo.mp4", "Identify timestamps where a visible consumer product appears, especially items that look branded or commercially packaged, such as skincare bottles, water bottles, cosmetics, food packaging, or electronics. Print out only the start and end timestamsp, don't say anything else.")
delete_video(asset_id)
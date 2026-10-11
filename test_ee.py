import os
import ee
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

project_id = os.getenv("EARTH_ENGINE_PROJECT") or os.getenv("EE_PROJECT_ID")
if not project_id:
    raise RuntimeError("Set EARTH_ENGINE_PROJECT in .env or environment.")

# Initialize Earth Engine with your configured project ID
ee.Initialize(project=project_id)
print(f"Earth Engine initialized successfully with project: {project_id}!")

# Define Nagpur point
nagpur_point = ee.Geometry.Point([79.0849, 21.1463])

# Test fetching a Landsat 8 image collection around Nagpur
collection = (
    ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
    .filterBounds(nagpur_point)
    .filterDate("2025-01-01", "2025-12-31")
)

print(f"Number of Landsat images found for Nagpur: {collection.size().getInfo()}")
import os
import vertexai
from google import genai
import logging
logging.basicConfig(level=logging.DEBUG)
os.environ['GOOGLE_CLOUD_PROJECT'] = 'multi-agent-dev-team-502213'
os.environ['GOOGLE_CLOUD_LOCATION'] = 'europe-west2'

client = genai.Client(vertexai=True, location='europe-west2')
print("Client created.")
try:
    response = client.models.generate_content(
        model='gemini-2.5-pro',
        contents='Hello',
    )
    print("2.5 pro ok:", response.text)
except Exception as e:
    print("2.5 Error:", e)

try:
    response = client.models.generate_content(
        model='gemini-3.1-pro',
        contents='Hello',
    )
    print("3.1 pro ok:", response.text)
except Exception as e:
    print("3.1 Error:", e)

import urllib.request
import json

# Define the target IP address
ip_address = "45.41.135.196"

# Construct the API endpoint URL
url = "".join(["http://ip-api.com/json/", ip_address])

try:
    # Send the web request
    with urllib.request.urlopen(url) as response:
        # Read and parse the JSON data
        data = json.loads(response.read().decode())
        
        # Check if the API request was successful
        if data.get("status") == "success":
            print(f"IP Address: {data.get('query')}")
            print(f"Country:    {data.get('country')} ({data.get('countryCode')})")
            print(f"Region/St:  {data.get('regionName')}")
            print(f"City:       {data.get('city')}")
        else:
            print("Failed to look up IP information.")
            
except Exception as e:
    print(f"An error occurred: {e}")

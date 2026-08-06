import re

import pandas as pd

# Path to the log file
log_file = '/media/phil/m2ssd/web/logs/www.philiplessner.com.access.log'

# Regular expression to parse the access log
# Format: IP - - [date/time +timezone] "request" status size referrer "user-agent" ...
pattern = r'(\d+\.\d+\.\d+\.\d+)\s+-\s+-\s+\[([^\]]+)\]\s+"([^"]+)"\s+(\d{3})\s+\d+\s+"-"\s+"([^"]+)"'

data = {
    'ip_address': [],
    'datetime': [],
    'request': [],
    'status_code': [],
    'user_agent': []
}

# Read and parse the log file
with open(log_file, 'r') as f:
    for line in f:
        match = re.search(pattern, line)
        if match:
            ip = match.group(1)
            datetime_str = match.group(2)
            request = match.group(3)
            status_code = match.group(4)
            user_agent = match.group(5)
            
            data['ip_address'].append(ip)
            data['datetime'].append(datetime_str)
            data['request'].append(request)
            data['status_code'].append(status_code)
            data['user_agent'].append(user_agent)

# Create DataFrame
df = pd.DataFrame(data)

# Convert datetime column to proper datetime format
df['datetime'] = pd.to_datetime(df['datetime'], format='%d/%b/%Y:%H:%M:%S %z')

# Filter for robots.txt requests with Google in user agent
mask = (df['request'].str.contains('robots.txt', case=False, na=False)) | \
        (df['user_agent'].str.contains('Google', case=False, na=False))

df_filtered = df[mask]
df = df[~mask]

print(f"Successfully parsed {len(df)} log entries")
print(f"Filtered dataframe shape: {df_filtered.shape}")
print(f"Remaining dataframe shape: {df.shape}")
print("\nFiltered records:")
print(df_filtered)
print("\nRemaining records:")
print(df)

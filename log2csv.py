import json
import urllib.request
from itertools import chain
import re
import pandas as pd


def logfile2df(log_file: str) -> pd.DataFrame:
    data = {
        'ip_address': [],
        'datetime': [],
        'request': [],
        'status_code': [],
        'user_agent': []
    }
    # Regular expression to parse the access log
    # Format: IP - - [date/time +timezone] "request" status size referrer "user-agent" ...
    pattern = r'(\d+\.\d+\.\d+\.\d+)\s+-\s+-\s+\[([^\]]+)\]\s+"([^"]+)"\s+(\d{3})\s+\d+\s+"-"\s+"([^"]+)"'
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
    return df


def filter_df(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Filter for robots.txt requests with Google in user agent
    mask = (df['request'].str.contains('robots.txt', case=False, na=False)) | \
            (df['user_agent'].str.contains('Google', case=False, na=False))

    df_filtered = df[mask]
    df = df[~mask]
    return df, df_filtered


def strings2jsonbytes(data: list[str]) -> bytes:
    '''
    Takes a list of utf-8 strings and returns json encoded as bytes
    '''
    return json.dumps(data).encode("utf-8")


def get_response(json_ips) -> list[dict]:
    '''
    Get geographic information from IP address via
    ip-api.com batch api whic can take up to 100 IP address
    Parameter 
    ---------
    json_ips: IP address encoded as json bytes
    Returns
    -------
    a list of dicts (one for each IP address) with the following fields:
    status, country, countryCode, region, regionName, city, zip, lat, long, timezone,
    isp, org, as, query(the IP addres)
    '''
    api = "http://ip-api.com/batch"
    req = urllib.request.Request(api, data=json_ips, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Python urllib")
    try:
        # Send the request and read the response
        with urllib.request.urlopen(req) as response:
            response_text = response.read().decode("utf-8")
            print("Response Status:", response.status)
            print("Response Body:\n", response_text)
            return json.loads(response_text)
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.reason}")
    except urllib.error.URLError as e:
        print(f"Connection Error: {e.reason}")


def ips2geo(ips: list[str], chunk_size: int = 100) -> list[dict]:
    '''
    Since the batch api at ip-api.com can only take 100 or less IP address at a time,
    we need to chunk the requests to be less than or equal to this size.
    Parameters
    ---------
    ips: List of IP address (as Python unicode strings) to get geographic information for
    chunk_size: how many requests to send to the batch api (must be less than or equal to 100)
    Returns
    --------
    list of dicts containing the geographic information
    '''
    size = len(ips)
    start = 0
    overall = []
    while (start+chunk_size < size):
        end = chunk_size + start
        json_ips_bytes = strings2jsonbytes(ips[start:end])
        print(f"Processed Elements {start} to {end}")
        api_response = get_response(json_ips_bytes)
        overall.append(api_response)
        start += chunk_size 
    json_ips_bytes =strings2jsonbytes(ips[start:])
    api_response = get_response(json_ips_bytes)
    overall.append(api_response)
    # Since overall is a list of lists of dict, flatten to list[dict]
    return list(chain.from_iterable(overall))


def response2df(ip_response: list[dict], df: pd.DataFrame) -> None:
    '''
    Append the columns of geographic information to the Pandas dataframe
    '''
    field_list = ["country", "countryCode", "region", "regionName", "city", "zip", "lat", "lon", "timezone"]
    for element in field_list:
        df[element] = [d.get(element, None) for d in ip_response]


if __name__ == "__main__":
    log_file = '/media/phil/m2ssd/web/logs/www.philiplessner.com.access.log'
    df = logfile2df(log_file)
    df_clean, df_robots = filter_df(df)
    ips = df_clean["ip_address"].to_list()
    geo_info = ips2geo(ips)
    response2df(geo_info, df_clean)
    df_robots.to_csv("./log_robots.csv")
    df_clean.to_csv("./log_clean.csv")


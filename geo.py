import json
import logging
import urllib.request
from itertools import chain

import pandas as pd

logger = logging.getLogger(__name__)


def get_ips(df: pd.DataFrame) -> list[str]:
    return df["ip_address"].to_list()


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
        logger.info("Processing elements %d to %d", start, end)
        api_response = get_response(json_ips_bytes)
        overall.append(api_response)
        start += chunk_size 
    json_ips_bytes =strings2jsonbytes(ips[start:])
    api_response = get_response(json_ips_bytes)
    overall.append(api_response)
    # Since overall is a list of lists of dict, flatten to list[dict]
    return list(chain.from_iterable(overall))


def response2df(ip_response: list[dict], df: pd.DataFrame) -> pd.DataFrame:
    '''
    Append the columns of geographic information to the Pandas dataframe
    '''
    dfc = df.copy()
    field_list = ["country", "countryCode", "region", "regionName", "city", "zip", "lat", "lon", "timezone"]
    for element in field_list:
        dfc.loc[:, element] = [d.get(element, None) for d in ip_response]
    dfc.astype(dtype={'status_code': 'Int64', 'lat': 'Float64', 'lon': 'Float64'})
    dfc['datetime'] = pd.to_datetime(dfc['datetime'])
    return dfc


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
            logger.info("Response status: %d", response.status)
            response_data = json.loads(response_text)
            logger.info("Number of geo records: %d", len(response_data))
            return response_data
    except urllib.error.HTTPError as e:
        logger.exception("HTTP error: %d - %s", e.code, e.reason)
        raise
    except urllib.error.URLError as e:
        logger.exception("Connection error: %s", e.reason)
        raise

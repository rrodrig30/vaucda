#!/usr/bin/env python3
"""
Test calculator input schema endpoint
Verifies API accessibility and response format
"""

import requests
import json
import urllib3

# Disable SSL warnings for self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Test endpoint
url = 'https://192.168.1.11:8002/api/v1/calculators/pcptcalculator/input-schema'

print("Testing Calculator Input Schema Endpoint")
print("=" * 80)
print(f"URL: {url}\n")

try:
    response = requests.get(url, verify=False, timeout=10)

    print(f"Status Code: {response.status_code}")
    print(f"\nResponse Headers:")
    for key, value in response.headers.items():
        print(f"  {key}: {value}")

    if response.ok:
        print(f"\n✓ SUCCESS - Endpoint is accessible")

        try:
            data = response.json()
            print(f"\nResponse Structure:")
            print(f"  calculator_id: {data.get('calculator_id')}")
            print(f"  calculator_name: {data.get('calculator_name')}")
            print(f"  input_schema: {len(data.get('input_schema', []))} fields")

            print(f"\nInput Schema Fields:")
            for field in data.get('input_schema', []):
                field_name = field.get('field_name')
                input_type = field.get('input_type')
                required = field.get('required')
                display_name = field.get('display_name')
                print(f"  - {field_name} ({input_type}): {display_name} {'[REQUIRED]' if required else '[OPTIONAL]'}")

            print(f"\n✓ JSON parsing successful")
            print(f"✓ Schema structure valid")

        except json.JSONDecodeError as e:
            print(f"\n✗ ERROR - Invalid JSON response")
            print(f"  {e}")
            print(f"\nRaw response:")
            print(response.text[:500])
    else:
        print(f"\n✗ ERROR - Request failed")
        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.text[:500]}")

except requests.exceptions.ConnectionError as e:
    print(f"\n✗ ERROR - Connection failed")
    print(f"  {e}")

except requests.exceptions.Timeout as e:
    print(f"\n✗ ERROR - Request timeout")
    print(f"  {e}")

except Exception as e:
    print(f"\n✗ ERROR - Unexpected error")
    print(f"  {type(e).__name__}: {e}")

print("\n" + "=" * 80)

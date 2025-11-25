#!/usr/bin/env python3
"""Test script to debug DLive API issues."""
import requests
import json
import sys

def test_dlive_api(permlink: str):
    """Test different GraphQL queries to find what works."""
    
    endpoint = "https://graphigo.prd.dlive.tv/"
    
    # Test 1: Original query
    print("=" * 60)
    print("TEST 1: Original Query")
    print("=" * 60)
    query1 = """
    query PastBroadcastPage($permlink: String!) {
        pastBroadcast(permlink: $permlink) {
            id
            title
            duration
            playbackUrl
            createdAt
            thumbnailUrl
            creator {
                displayname
                username
            }
        }
    }
    """
    
    payload1 = {
        "operationName": "PastBroadcastPage",
        "variables": {"permlink": permlink},
        "query": query1
    }
    
    try:
        response = requests.post(endpoint, json=payload1, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Body:")
        print(json.dumps(response.json(), indent=2))
    except Exception as e:
        print(f"Error: {e}")
        print(f"Response Text: {response.text if 'response' in locals() else 'N/A'}")
    
    print("\n")
    
    # Test 2: Simpler query
    print("=" * 60)
    print("TEST 2: Simplified Query")
    print("=" * 60)
    query2 = """
    query {
        pastBroadcast(permlink: "%s") {
            title
            playbackUrl
        }
    }
    """ % permlink
    
    payload2 = {
        "query": query2
    }
    
    try:
        response = requests.post(endpoint, json=payload2, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body:")
        print(json.dumps(response.json(), indent=2))
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n")
    
    # Test 3: Alternative query structure
    print("=" * 60)
    print("TEST 3: Alternative Query")
    print("=" * 60)
    query3 = """
    query GetVideo($permlink: String!) {
        video(permlink: $permlink) {
            title
            playback
        }
    }
    """
    
    payload3 = {
        "operationName": "GetVideo",
        "variables": {"permlink": permlink},
        "query": query3
    }
    
    try:
        response = requests.post(endpoint, json=payload3, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body:")
        print(json.dumps(response.json(), indent=2))
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_api.py <permlink_or_url>")
        print("Example: python test_api.py 'example-video-123'")
        print("Or: python test_api.py 'https://dlive.tv/p/example-video-123'")
        sys.exit(1)
    
    input_str = sys.argv[1]
    
    # Extract permlink if URL provided
    if "dlive.tv" in input_str:
        permlink = input_str.rstrip("/").split("/")[-1]
    else:
        permlink = input_str
    
    print(f"Testing with permlink: {permlink}\n")
    test_dlive_api(permlink)


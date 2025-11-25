#!/usr/bin/env python3
"""Test which GraphQL fields are available."""
import requests
import json

def test_fields():
    endpoint = "https://graphigo.prd.dlive.tv/"
    permlink = "uzayzuhal+Sa-qcgkvR"
    
    # Test all possible fields one by one
    fields_to_test = [
        "id",
        "title",
        "playbackUrl",
        "createdAt",
        "thumbnailUrl",
        "length",
        "viewCount",
        "creator { displayname username }",
    ]
    
    working_fields = []
    
    for field in fields_to_test:
        query = f"""
        query {{
            pastBroadcast(permlink: "{permlink}") {{
                {field}
            }}
        }}
        """
        
        try:
            response = requests.post(endpoint, json={"query": query}, timeout=10)
            data = response.json()
            
            if "errors" not in data:
                print(f"✅ {field}")
                working_fields.append(field)
            else:
                print(f"❌ {field}: {data['errors'][0]['message']}")
        except Exception as e:
            print(f"⚠️  {field}: {e}")
    
    print("\n" + "="*60)
    print("WORKING QUERY:")
    print("="*60)
    working_query = "query PastBroadcastPage($permlink: String!) { pastBroadcast(permlink: $permlink) { " + " ".join(working_fields) + " } }"
    print(working_query)
    
    print("\n" + "="*60)
    print("TEST WITH FULL WORKING QUERY:")
    print("="*60)
    
    response = requests.post(
        endpoint,
        json={
            "operationName": "PastBroadcastPage",
            "variables": {"permlink": permlink},
            "query": working_query
        },
        timeout=10
    )
    
    print(json.dumps(response.json(), indent=2))

if __name__ == "__main__":
    test_fields()


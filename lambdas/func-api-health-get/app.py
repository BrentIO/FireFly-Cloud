import json

def health(event, context):

    body = {"status":"OK"}

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, indent=4)
    }
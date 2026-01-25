import requests
import json
import sys

def analyze_logs_stream(text: str, files: list[str], api_url: str = "http://127.0.0.1:5001/analyze"):
    """
    Calls the log analysis API and yields the streaming response.
    
    Args:
        text (str): The Jira description or summary text.
        files (list[str]): List of absolute paths to log files.
        api_url (str): The URL of the analysis API.
        
    Yields:
        dict: The parsed JSON response objects from the stream.
    """
    payload = {
        "text": text,
        "files": files
    }
    
    print(f"Connecting to {api_url}...", file=sys.stderr)
    
    try:
        with requests.post(api_url, json=payload, stream=True) as response:
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    try:
                        data = json.loads(decoded_line)
                        yield data
                    except json.JSONDecodeError:
                        print(f"[Warning] Could not parse JSON: {decoded_line}", file=sys.stderr)
                        
    except requests.exceptions.ConnectionError:
        yield {"event": "error", "error": "Connection failed. Is the server running?"}
    except Exception as e:
        yield {"event": "error", "error": str(e)}

def print_analysis_result(text, files):
    print(f"--- Starting Analysis Request ---")
    print(f"Text Input: {text[:100]}..." if len(text) > 100 else f"Text Input: {text}")
    print(f"Files Input: {files}")
    print("-" * 30)
    
    for item in analyze_logs_stream(text, files):
        event = item.get("event")
        # Extract content based on event type preference
        content = item.get("content") or item.get("status") or item.get("warning") or item.get("error")
        
        # Print formatted output
        if event == "status":
            print(f"[STATUS] {content}")
        elif event == "content":
            # For content, we might want to print it as is, or handle newlines
            print(f"[CONTENT] {content}")
        elif event == "warning":
            print(f"[WARNING] {content}")
        elif event == "error":
            print(f"[ERROR] {content}")
        else:
            # Fallback for other events
            print(f"[{event}] {item}")

#写一个def analyze_logs_stream(text: str, files: list[str], api_url: str = "http://127.0.0.1:5001/analyze"): 这个的demo函数，返回stream流式输出，打印出每个item
# def analyze_logs_stream(text: str, files: list[str], api_url: str = "http://127.0.0.1:5001/analyze"):
#     """
#     Calls the log analysis API and yields the streaming response.
    
#     Args:
#         text (str): The Jira description or summary text.
#         files (list[str]): List of absolute paths to log files.
#         api_url (str): The URL of the analysis API.
        
#     Yields:
#         dict: The parsed JSON response objects from the stream.
#     """
#     #做一个假的yeild的输出包括status, content, warning, error，要流式输出的，每个item之间间隔1秒
#     import time
#     yield {"event": "status", "body": "Analysis started"}
#     time.sleep(1)
#     yield {"event": "warning", "body": "This is a warning message"}
#     time.sleep(1)
#     yield {"event": "error", "body": "This is an error message"}
#     time.sleep(1)
#     yield {"event": "status", "body": "Analysis completed"}
#     time.sleep(1)
#     yield {"event": "content", "body": "Analysis completed successfully"}

if __name__ == "__main__":
    # Example usage data
    # You can update these values to test with real data
    test_text = "OTT-90829"
    
    # Add absolute paths to log files here if you want to test log analysis
    # e.g., ["C:\\logs\\system.log"]
    test_files = [] 
    
    print_analysis_result(test_text, test_files)

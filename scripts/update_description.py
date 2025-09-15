import os
from dotenv import load_dotenv
import requests
import json
from datetime import datetime, timezone
import logging
from logging.handlers import RotatingFileHandler
import time

# 设置日志
logger = logging.getLogger('habitica_update_description')
logger.setLevel(logging.DEBUG)

handler = RotatingFileHandler('logs/update_description.log', maxBytes=1024*1024, backupCount=1)
handler.setLevel(logging.DEBUG)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logger.addHandler(handler)
logger.addHandler(console_handler)

load_dotenv()
HABITICA_USER_ID = os.getenv("HABITICA_USER_ID")
HABITICA_API_KEY = os.getenv("HABITICA_API_KEY")

# 全局变量
last_request_time = 0
request_interval = 2  # 默认请求间隔为1秒

def rate_limited_request(method, url, **kwargs):
    global last_request_time
    wait_time = max(0, request_interval - (time.time() - last_request_time))
    if wait_time > 0:
        # logger.debug(f"Rate limit enforced, waiting for {wait_time:.2f} seconds.")
        time.sleep(wait_time)
    response = method(url, **kwargs)
    last_request_time = time.time()
    logger.debug(f"Request: {method} {url}")
    return response

def get_json_response(response):
    try:
        return response.json()
    except json.JSONDecodeError:
        logger.error("Invalid JSON response received.")
        return None

def log_response_error(response, action):
    logger.error(f"{action} failed: Status code {response.status_code}\nHeaders: {response.headers}\nText: {response.text}")

def get_daily_sentence():
    url = "https://sentence.iciba.com/?c=dailysentence&m=getTodaySentence"
    response = rate_limited_request(requests.get, url)
    if response:
        return get_json_response(response)
    else:
        log_response_error(response, "Getting party data")
        return {}

def get_habitica_party_data(headers):
    url = "https://habitica.com/api/v3/groups/party/members"
    response = rate_limited_request(requests.get, url, headers=headers)

    if response and response.status_code == 200:
        data = []
        members = get_json_response(response).get('data', [])
        for member in members:
            member_data = get_member_details(member, headers)
            if member_data:
                data.append(member_data)
        return data
    else:
        log_response_error(response, "Getting party data")
        return []

def get_member_details(member, headers):
    member_id = member['id']
    url = f'https://habitica.com/api/v3/members/{member_id}'
    member_response = rate_limited_request(requests.get, url, headers=headers)
    if member_response and member_response.status_code == 200:
        member_details = get_json_response(member_response).get('data', {})
        last_login = member_details['auth']['timestamps']['updated']
        duration = calculate_duration(last_login)
        since_last_login = format_duration(duration)
        return {"name": member['profile']['name'], "last_login": last_login, "duration": duration, "since_last_login": since_last_login}
    else:
        log_response_error(member_response, "Getting details for member")
        return None

def calculate_duration(last_login_time_str):
    last_login_time = datetime.strptime(last_login_time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    last_login_time = last_login_time.replace(tzinfo=timezone.utc)
    current_time = datetime.now(timezone.utc)
    return current_time - last_login_time

def format_duration(duration):
    days = duration.days
    hours, remainder = divmod(duration.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    time_parts = []
    if days:
        time_parts.append(f"{days}d")
    if hours:
        time_parts.append(f"{hours}h")
    if minutes:
        time_parts.append(f"{minutes}m")
    
    return ' '.join(time_parts) if time_parts else "just now"

def format_current_time():
    return datetime.now(timezone.utc).strftime('%m-%d %I:%M %p, %Z')

def update_party_description(content, translation, members_str, time_str, headers):
    url = "https://habitica.com/api/v3/groups/party"
    try:
        with open("documents/brief_description.md", "r") as f:
            template = f.read()
        description = template.format(content=content, translation=translation, members_str=members_str, time_str=time_str)
        data = {"description": description}

        response = rate_limited_request(requests.put, url, headers=headers, json=data)
        if response:
            logger.info("Party description updated successfully.")
        else:
            log_response_error(response, "Getting party data")
    except Exception as e:
        logger.error(f"An error occurred while updating the party description: {e}")

def main():
    logger.info("Starting Habitica party management script: update_description.")

    headers = {
        "x-api-user": HABITICA_USER_ID,
        "x-api-key": HABITICA_API_KEY,
        "x-client": HABITICA_USER_ID + "-AutomatePartyManagement",
        "Content-Type": "application/json"
    }

    daily_sentence = get_daily_sentence()
    content = daily_sentence.get('content', '')
    translation = daily_sentence.get('note', '')

    members_list = sorted(get_habitica_party_data(headers), key=lambda x: x['duration'])
    members_str = '\n\n'.join(
        f"{index + 1}. {item['name']}:  {item['since_last_login']}" for index, item in enumerate(members_list)
    )

    time_str = format_current_time()

    update_party_description(content, translation, members_str, time_str, headers)

if __name__ == "__main__":
    main()

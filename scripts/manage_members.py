import os
from dotenv import load_dotenv
import requests
import json
from datetime import datetime, timezone, timedelta
import logging
from logging.handlers import RotatingFileHandler
import time

logger = logging.getLogger('habitica_manage_members')
logger.setLevel(logging.DEBUG)

handler = RotatingFileHandler('./logs/manage_members.log', maxBytes=1024*1024, backupCount=1)
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

last_request_time = 0
request_interval = 2

time_limit = timedelta(days=4)

headers = {
    "x-api-user": HABITICA_USER_ID,
    "x-api-key": HABITICA_API_KEY,
    "x-client": HABITICA_USER_ID + "-AutomatePartyManagement",
    "Content-Type": "application/json"
}

with open("./documents/new_members.md", "r") as f:
    template_new = f.read()

with open("./documents/remove_PM.md", "r") as f:
    template_message = f.read()

with open("./documents/remove_members.md", "r") as f:
    template_remove = f.read()

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

def send_message_to_user(user_id, message):
    url = "https://habitica.com/api/v3/members/send-private-message"
    message_data = {
        "message": message,
        "toUserId": user_id
    }
    response = rate_limited_request(requests.post, url, headers=headers, json=message_data)
    if response.status_code == 200:
        logger.info(f"Message sent to user {user_id}.")
    else:
        log_response_error(response, f"Sending message to user {user_id}")

def send_invite(id_list, name_list):
    url = "https://habitica.com/api/v3/groups/party/invite"
    data = {"uuids": id_list}
    response = rate_limited_request(requests.post, url, json=data, headers=headers)
    if response.status_code == 200:
        id_str = '\n\n'.join([f"- [{name}](https://habitica.com/profile/{id})" for name, id in zip(name_list, id_list)])
        message = template_new.format(list_str=id_str)
        send_party_chat(message)
        logger.info(f"Invitations sent to {name_list}.")
    else:
        log_response_error(response, "Sending invitations")

def send_party_chat(message):
    url = "https://habitica.com/api/v3/groups/party/chat"
    data = {"message": message}
    response = rate_limited_request(requests.post, url, json=data, headers=headers)
    if response.status_code == 200:
        logger.info(f"Party chat message sent: {message}.")
    else:
        log_response_error(response, "Sending party chat message")

def get_inactive_party_members(time_limit):
    url = "https://habitica.com/api/v3/groups/party/members"
    response = rate_limited_request(requests.get, url, headers=headers)
    if response.status_code == 200:
        data = []
        members = get_json_response(response).get('data', [])
        for member in members:
            member_id = member['id']
            member_response = rate_limited_request(requests.get, f'https://habitica.com/api/v3/members/{member_id}', headers=headers)
            if member_response.status_code == 200:
                member_data = get_json_response(member_response).get('data', {})
                last_login = member_data['auth']['timestamps']['updated']
                if calculate_duration(last_login) >= time_limit:
                    data.append({
                        "id": member_id,
                        "name": member_data['profile']['name']
                    })
            else:
                log_response_error(member_response, f"Fetching details for member {member_id}")
        return data
    else:
        log_response_error(response, "Fetching party members")
        return []

def remove_users_from_party(user_to_remove):
    url = "https://habitica.com/api/v3/groups/party/removeMember/{id}"
    for user in user_to_remove:
        send_message_to_user(user['id'], template_message.format(name=user['name']))
        response = rate_limited_request(requests.post, url.format(id=user['id']), headers=headers)
        send_party_chat(template_remove.format(name=user['name'], id=user['id']))
        if response.status_code == 200:
            logger.info(f"User {user} has been removed from the party.")
        else:
            log_response_error(response, f"Removing user {user} from the party")

def search_and_invite_users():
    url = "https://habitica.com/api/v3/looking-for-party"
    response = rate_limited_request(requests.get, url, headers=headers)
    if response.status_code == 200:
        groups = get_json_response(response).get('data', [])
        id_list = [group['_id'] for group in groups]
        name_list = [group['profile']['name'] for group in groups]
        if id_list:
            send_invite(id_list, name_list)
    else:
        log_response_error(response, "Fetching users looking for party")

def calculate_duration(last_login_time_str):
    last_login_time = datetime.strptime(last_login_time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    last_login_time = last_login_time.replace(tzinfo=timezone.utc)
    current_time = datetime.now(timezone.utc)
    return current_time - last_login_time

def main():
    logger.info("Starting Habitica party management script: manage_members.")
    remove_id_list = get_inactive_party_members(time_limit)
    if remove_id_list:
        remove_users_from_party(remove_id_list)
    search_and_invite_users()
    logger.info("Habitica party management script completed successfully.")

if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR = BASE_DIR / "documents"
LOGS_DIR = BASE_DIR / "logs"
STATE_DIR = BASE_DIR / "state"
INVITE_QUEUE_PATH = STATE_DIR / "invite_queue.json"
ROOT_ENV_PATH = BASE_DIR / ".env"
LEGACY_ENV_PATH = BASE_DIR / "scripts" / ".env"

REQUEST_INTERVAL_SECONDS = 2
INACTIVE_TIME_LIMIT = timedelta(days=4)
PARTY_MEMBER_LIMIT = 30
PARTY_PENDING_LIMIT = 10
GROUP_PAGE_SIZE = 60

LOGS_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("habitica_manage_members")
logger.setLevel(logging.DEBUG)
logger.propagate = False

if not logger.handlers:
    file_handler = RotatingFileHandler(
        LOGS_DIR / "manage_members.log",
        maxBytes=1024 * 1024,
        backupCount=1,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def load_environment() -> None:
    # Keep supporting the original scripts/.env location while preferring repo-root .env.
    load_dotenv(LEGACY_ENV_PATH, override=False)
    load_dotenv(ROOT_ENV_PATH, override=True)


load_environment()
HABITICA_USER_ID = os.getenv("HABITICA_USER_ID")
HABITICA_API_KEY = os.getenv("HABITICA_API_KEY")

TEMPLATE_NEW = (DOCUMENTS_DIR / "new_members.md").read_text(encoding="utf-8")
TEMPLATE_MESSAGE = (DOCUMENTS_DIR / "remove_PM.md").read_text(encoding="utf-8")
TEMPLATE_REMOVE = (DOCUMENTS_DIR / "remove_members.md").read_text(encoding="utf-8")

last_request_time = 0.0


def validate_configuration() -> None:
    missing = [
        name
        for name, value in (
            ("HABITICA_USER_ID", HABITICA_USER_ID),
            ("HABITICA_API_KEY", HABITICA_API_KEY),
        )
        if not value
    ]
    if missing:
        missing_text = ", ".join(missing)
        raise RuntimeError(f"Missing required environment variables: {missing_text}")


def ensure_runtime_files() -> None:
    STATE_DIR.mkdir(exist_ok=True)
    if not INVITE_QUEUE_PATH.exists():
        INVITE_QUEUE_PATH.write_text("[]\n", encoding="utf-8")


def build_headers() -> dict[str, str]:
    validate_configuration()
    return {
        "x-api-user": HABITICA_USER_ID,
        "x-api-key": HABITICA_API_KEY,
        "x-client": f"{HABITICA_USER_ID}-AutomatePartyManagement",
        "Content-Type": "application/json",
    }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp_now() -> str:
    return utc_now().isoformat()


def rate_limited_request(method: Callable[..., requests.Response], url: str, **kwargs: Any) -> requests.Response:
    global last_request_time

    wait_time = max(0.0, REQUEST_INTERVAL_SECONDS - (time.time() - last_request_time))
    if wait_time > 0:
        time.sleep(wait_time)

    kwargs.setdefault("timeout", 30)
    response = method(url, **kwargs)
    last_request_time = time.time()
    logger.debug("Request: %s %s", method.__name__.upper(), url)
    return response


def get_json_response(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        logger.error("Invalid JSON response received.")
        return {}
    return payload if isinstance(payload, dict) else {}


def get_response_data(response: requests.Response, default: Any) -> Any:
    payload = get_json_response(response)
    return payload.get("data", default)


def log_response_error(response: requests.Response | None, action: str) -> None:
    if response is None:
        logger.error("%s failed: no response received.", action)
        return

    logger.error(
        "%s failed: Status code %s; Headers: %s; Text: %s",
        action,
        response.status_code,
        response.headers,
        response.text,
    )


def extract_user_id(item: dict[str, Any]) -> str | None:
    user_id = item.get("id") or item.get("_id")
    return str(user_id) if user_id else None


def extract_user_name(item: dict[str, Any], fallback: str = "") -> str:
    return item.get("profile", {}).get("name") or fallback


def parse_habitica_timestamp(value: str) -> datetime:
    formats = ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ")
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Unsupported Habitica timestamp format: {value}")


def calculate_duration(last_login_time_str: str) -> timedelta:
    last_login_time = parse_habitica_timestamp(last_login_time_str)
    return utc_now() - last_login_time


def member_ids_for_activity_check(
    party_members: list[dict[str, str]], own_user_id: str | None
) -> list[str]:
    return [
        member["id"]
        for member in party_members
        if member.get("id") and member.get("id") != own_user_id
    ]


def calculate_available_invite_slots(member_count: int, pending_count: int) -> int:
    member_slots = PARTY_MEMBER_LIMIT - member_count - pending_count
    pending_slots = PARTY_PENDING_LIMIT - pending_count
    return max(0, min(member_slots, pending_slots))


def get_pending_invite_queue_records(
    invite_queue: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return sorted(
        [record for record in invite_queue if record.get("status") == "pending"],
        key=lambda record: (record.get("invited_at") or "", record.get("user_id") or ""),
    )


def merge_pending_user_ids(
    api_pending_ids: set[str], invite_queue: list[dict[str, Any]]
) -> set[str]:
    tracked_pending_ids = {
        record["user_id"]
        for record in invite_queue
        if record.get("status") == "pending" and record.get("user_id")
    }
    return set(api_pending_ids) | tracked_pending_ids


def filter_invitable_candidates(
    candidates: list[dict[str, str]],
    own_user_id: str | None,
    member_ids: set[str],
    pending_ids: set[str],
) -> list[dict[str, str]]:
    blocked_ids = set(member_ids) | set(pending_ids)
    if own_user_id:
        blocked_ids.add(own_user_id)

    filtered: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for candidate in candidates:
        user_id = candidate.get("id")
        if not user_id or user_id in blocked_ids or user_id in seen_ids:
            continue
        seen_ids.add(user_id)
        filtered.append(candidate)
    return filtered


def load_invite_queue() -> list[dict[str, Any]]:
    ensure_runtime_files()
    try:
        raw_data = json.loads(INVITE_QUEUE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Invite queue is not valid JSON. Starting with an empty queue.")
        return []

    if not isinstance(raw_data, list):
        logger.warning("Invite queue root is not a list. Starting with an empty queue.")
        return []

    queue: list[dict[str, Any]] = []
    for item in raw_data:
        if not isinstance(item, dict) or not item.get("user_id"):
            continue
        record = dict(item)
        record["user_id"] = str(record["user_id"])
        record["name"] = record.get("name") or record["user_id"]
        record["status"] = record.get("status") or "pending"
        queue.append(record)
    return queue


def save_invite_queue(invite_queue: list[dict[str, Any]]) -> None:
    ensure_runtime_files()
    sorted_queue = sorted(
        invite_queue,
        key=lambda record: (record.get("invited_at") or "", record.get("user_id") or ""),
    )
    INVITE_QUEUE_PATH.write_text(
        json.dumps(sorted_queue, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def update_invite_record(
    invite_queue: list[dict[str, Any]],
    user_id: str,
    name: str,
    status: str,
    note: str = "",
) -> dict[str, Any]:
    record = next((item for item in invite_queue if item.get("user_id") == user_id), None)
    timestamp = timestamp_now()

    if record is None:
        record = {"user_id": user_id}
        invite_queue.append(record)

    record["user_id"] = user_id
    record["name"] = name or record.get("name") or user_id
    record["status"] = status
    record["updated_at"] = timestamp

    if status == "pending":
        record["invited_at"] = timestamp
        record.pop("resolved_at", None)
    else:
        record["resolved_at"] = timestamp

    if note:
        record["note"] = note

    return record


def reconcile_invite_queue(
    invite_queue: list[dict[str, Any]],
    member_ids: set[str],
    api_pending_ids: set[str],
    member_fetcher: Callable[[str], dict[str, Any] | None],
) -> None:
    for record in invite_queue:
        user_id = record.get("user_id")
        if not user_id:
            continue

        if user_id in member_ids:
            update_invite_record(
                invite_queue,
                user_id,
                record.get("name", user_id),
                "joined",
                "User joined the current party.",
            )
            continue

        if record.get("status") != "pending":
            continue

        if user_id in api_pending_ids:
            record["updated_at"] = timestamp_now()
            continue

        member_profile = member_fetcher(user_id)
        if member_profile and member_profile.get("party", {}).get("_id"):
            update_invite_record(
                invite_queue,
                user_id,
                extract_user_name(member_profile, record.get("name", user_id)),
                "joined_other_party",
                "User joined another party before accepting this invite.",
            )


def get_party_members() -> list[dict[str, str]]:
    response = rate_limited_request(
        requests.get,
        "https://habitica.com/api/v3/groups/party/members",
        headers=build_headers(),
    )
    if response.status_code != 200:
        log_response_error(response, "Fetching party members")
        return []

    members = get_response_data(response, [])
    if not isinstance(members, list):
        return []

    party_members: list[dict[str, str]] = []
    for member in members:
        user_id = extract_user_id(member)
        if not user_id:
            continue
        party_members.append(
            {"id": user_id, "name": extract_user_name(member, user_id)}
        )
    return party_members


def get_member_profile(member_id: str) -> dict[str, Any] | None:
    response = rate_limited_request(
        requests.get,
        f"https://habitica.com/api/v3/members/{member_id}",
        headers=build_headers(),
    )
    if response.status_code != 200:
        log_response_error(response, f"Fetching details for member {member_id}")
        return None

    member_profile = get_response_data(response, {})
    return member_profile if isinstance(member_profile, dict) else None


def get_current_party_invites() -> list[dict[str, str]]:
    invites: list[dict[str, str]] = []
    last_id: str | None = None

    while True:
        params: dict[str, Any] = {"limit": GROUP_PAGE_SIZE}
        if last_id:
            params["lastId"] = last_id

        response = rate_limited_request(
            requests.get,
            "https://habitica.com/api/v3/groups/party/invites",
            headers=build_headers(),
            params=params,
        )
        if response.status_code != 200:
            log_response_error(response, "Fetching current party invites")
            break

        batch = get_response_data(response, [])
        if not isinstance(batch, list) or not batch:
            break

        for member in batch:
            user_id = extract_user_id(member)
            if not user_id:
                continue
            invites.append({"id": user_id, "name": extract_user_name(member, user_id)})

        if len(batch) < GROUP_PAGE_SIZE:
            break

        last_id = extract_user_id(batch[-1])
        if not last_id:
            break

    return invites


def get_looking_for_party_users() -> list[dict[str, str]]:
    response = rate_limited_request(
        requests.get,
        "https://habitica.com/api/v3/looking-for-party",
        headers=build_headers(),
    )
    if response.status_code != 200:
        log_response_error(response, "Fetching users looking for party")
        return []

    groups = get_response_data(response, [])
    if not isinstance(groups, list):
        return []

    users: list[dict[str, str]] = []
    for group in groups:
        user_id = extract_user_id(group)
        if not user_id:
            continue
        users.append({"id": user_id, "name": extract_user_name(group, user_id)})
    return users


def send_message_to_user(user_id: str, message: str) -> None:
    response = rate_limited_request(
        requests.post,
        "https://habitica.com/api/v3/members/send-private-message",
        headers=build_headers(),
        json={"message": message, "toUserId": user_id},
    )
    if response.status_code == 200:
        logger.info("Message sent to user %s.", user_id)
        return
    log_response_error(response, f"Sending message to user {user_id}")


def send_party_chat(message: str) -> None:
    response = rate_limited_request(
        requests.post,
        "https://habitica.com/api/v3/groups/party/chat",
        headers=build_headers(),
        json={"message": message},
    )
    if response.status_code == 200:
        logger.info("Party chat message sent.")
        return
    log_response_error(response, "Sending party chat message")


def remove_party_user(user_id: str) -> requests.Response:
    return rate_limited_request(
        requests.post,
        f"https://habitica.com/api/v3/groups/party/removeMember/{user_id}",
        headers=build_headers(),
    )


def send_invite(user_id: str, name: str) -> bool:
    response = rate_limited_request(
        requests.post,
        "https://habitica.com/api/v3/groups/party/invite",
        headers=build_headers(),
        json={"uuids": [user_id]},
    )
    if response.status_code == 200:
        logger.info("Invitation sent to %s (%s).", name, user_id)
        return True

    log_response_error(response, f"Sending invitation to {name} ({user_id})")
    return False


def send_invite_summary(invited_users: list[dict[str, str]]) -> None:
    if not invited_users:
        return

    list_str = "\n\n".join(
        f"- [{user['name']}](https://habitica.com/profile/{user['id']})"
        for user in invited_users
    )
    send_party_chat(TEMPLATE_NEW.format(list_str=list_str))


def get_inactive_party_members(
    party_members: list[dict[str, str]],
    time_limit: timedelta,
    own_user_id: str | None,
    member_fetcher: Callable[[str], dict[str, Any] | None],
) -> list[dict[str, str]]:
    inactive_members: list[dict[str, str]] = []

    for member_id in member_ids_for_activity_check(party_members, own_user_id):
        member_profile = member_fetcher(member_id)
        if not member_profile:
            continue

        last_login = member_profile.get("auth", {}).get("timestamps", {}).get("updated")
        if not last_login:
            logger.warning("Skipping member %s because last login timestamp is missing.", member_id)
            continue

        if calculate_duration(last_login) >= time_limit:
            inactive_members.append(
                {
                    "id": member_id,
                    "name": extract_user_name(member_profile, member_id),
                }
            )

    return inactive_members


def remove_users_from_party(users_to_remove: list[dict[str, str]]) -> None:
    for user in users_to_remove:
        send_message_to_user(user["id"], TEMPLATE_MESSAGE.format(name=user["name"]))
        response = remove_party_user(user["id"])
        if response.status_code == 200:
            send_party_chat(TEMPLATE_REMOVE.format(name=user["name"], id=user["id"]))
            logger.info("User %s has been removed from the party.", user)
        else:
            log_response_error(response, f"Removing user {user} from the party")


def remove_pending_invite(user_id: str, name: str) -> str:
    response = remove_party_user(user_id)
    if response.status_code == 200:
        logger.info("Pending invite removed for %s (%s) to free capacity.", name, user_id)
        return "cancelled"

    if response.status_code == 404:
        logger.info(
            "Pending invite for %s (%s) no longer exists. Treating it as already cleared.",
            name,
            user_id,
        )
        return "expired"

    log_response_error(response, f"Removing pending invite for {name} ({user_id})")
    return "error"


def free_capacity_for_new_invites(
    invite_queue: list[dict[str, Any]],
    member_count: int,
    effective_pending_ids: set[str],
) -> int:
    available_slots = calculate_available_invite_slots(member_count, len(effective_pending_ids))

    while available_slots == 0:
        cleanup_candidates = [
            record
            for record in get_pending_invite_queue_records(invite_queue)
            if record.get("user_id") in effective_pending_ids
        ]
        if not cleanup_candidates:
            break

        oldest_invite = cleanup_candidates[0]
        user_id = oldest_invite["user_id"]
        name = oldest_invite.get("name", user_id)

        cleanup_result = remove_pending_invite(user_id, name)
        if cleanup_result == "error":
            break

        effective_pending_ids.discard(user_id)
        if cleanup_result == "cancelled":
            update_invite_record(
                invite_queue,
                user_id,
                name,
                "cancelled",
                "Removed automatically to free invitation capacity.",
            )
        else:
            update_invite_record(
                invite_queue,
                user_id,
                name,
                "expired",
                "Invite was already inactive during capacity cleanup.",
            )
        save_invite_queue(invite_queue)

        available_slots = calculate_available_invite_slots(member_count, len(effective_pending_ids))

    return available_slots


def invite_new_users(
    invite_queue: list[dict[str, Any]],
    candidates: list[dict[str, str]],
) -> list[dict[str, str]]:
    invited_users: list[dict[str, str]] = []

    for candidate in candidates:
        if send_invite(candidate["id"], candidate["name"]):
            invited_users.append(candidate)
            update_invite_record(
                invite_queue,
                candidate["id"],
                candidate["name"],
                "pending",
                "Invited by automation.",
            )

    if invited_users:
        save_invite_queue(invite_queue)
        send_invite_summary(invited_users)

    return invited_users


def search_and_invite_users(
    invite_queue: list[dict[str, Any]],
    party_members: list[dict[str, str]],
    member_fetcher: Callable[[str], dict[str, Any] | None],
) -> None:
    current_invites = get_current_party_invites()
    api_pending_ids = {invite["id"] for invite in current_invites}
    member_ids = {member["id"] for member in party_members}

    reconcile_invite_queue(invite_queue, member_ids, api_pending_ids, member_fetcher)
    save_invite_queue(invite_queue)

    effective_pending_ids = merge_pending_user_ids(api_pending_ids, invite_queue)
    available_slots = free_capacity_for_new_invites(
        invite_queue,
        len(party_members),
        effective_pending_ids,
    )

    if available_slots == 0:
        logger.info(
            "Skipping invitations because the party has no safe capacity left. "
            "Members=%s, effective pending=%s.",
            len(party_members),
            len(effective_pending_ids),
        )
        return

    candidates = filter_invitable_candidates(
        get_looking_for_party_users(),
        HABITICA_USER_ID,
        member_ids,
        effective_pending_ids,
    )
    if not candidates:
        logger.info("No eligible users found for invitation.")
        return

    invited_users = invite_new_users(invite_queue, candidates[:available_slots])
    if invited_users:
        logger.info("Invited %s user(s).", len(invited_users))
    else:
        logger.info("No invitations were sent successfully.")


def main() -> None:
    validate_configuration()
    ensure_runtime_files()

    logger.info("Starting Habitica party management script: manage_members.")

    invite_queue = load_invite_queue()
    member_cache: dict[str, dict[str, Any] | None] = {}

    def cached_member_fetcher(member_id: str) -> dict[str, Any] | None:
        if member_id not in member_cache:
            member_cache[member_id] = get_member_profile(member_id)
        return member_cache[member_id]

    party_members = get_party_members()
    inactive_members = get_inactive_party_members(
        party_members,
        INACTIVE_TIME_LIMIT,
        HABITICA_USER_ID,
        cached_member_fetcher,
    )
    if inactive_members:
        remove_users_from_party(inactive_members)
        party_members = get_party_members()

    search_and_invite_users(invite_queue, party_members, cached_member_fetcher)
    logger.info("Habitica party management script completed successfully.")


if __name__ == "__main__":
    main()

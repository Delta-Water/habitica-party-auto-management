import unittest

from scripts.manage_members import (
    calculate_available_invite_slots,
    filter_invitable_candidates,
    get_pending_invite_queue_records,
    member_ids_for_activity_check,
    merge_pending_user_ids,
    reconcile_invite_queue,
)


class ManageMembersTests(unittest.TestCase):
    def test_member_ids_for_activity_check_excludes_self(self) -> None:
        party_members = [
            {"id": "self-user", "name": "Self"},
            {"id": "other-user", "name": "Other"},
        ]

        result = member_ids_for_activity_check(party_members, "self-user")

        self.assertEqual(result, ["other-user"])

    def test_calculate_available_invite_slots_respects_both_limits(self) -> None:
        self.assertEqual(calculate_available_invite_slots(30, 0), 0)
        self.assertEqual(calculate_available_invite_slots(20, 8), 2)
        self.assertEqual(calculate_available_invite_slots(25, 5), 0)

    def test_merge_pending_user_ids_includes_tracked_pending_users(self) -> None:
        invite_queue = [
            {"user_id": "tracked-user", "status": "pending", "invited_at": "2026-03-27T00:00:00+00:00"},
            {"user_id": "done-user", "status": "cancelled", "invited_at": "2026-03-26T00:00:00+00:00"},
        ]

        result = merge_pending_user_ids({"api-user"}, invite_queue)

        self.assertEqual(result, {"api-user", "tracked-user"})

    def test_get_pending_invite_queue_records_returns_oldest_first(self) -> None:
        invite_queue = [
            {"user_id": "new-user", "status": "pending", "invited_at": "2026-03-28T00:00:00+00:00"},
            {"user_id": "old-user", "status": "pending", "invited_at": "2026-03-27T00:00:00+00:00"},
            {"user_id": "done-user", "status": "cancelled", "invited_at": "2026-03-26T00:00:00+00:00"},
        ]

        result = get_pending_invite_queue_records(invite_queue)

        self.assertEqual([record["user_id"] for record in result], ["old-user", "new-user"])

    def test_reconcile_invite_queue_marks_users_in_other_party_as_non_pending(self) -> None:
        invite_queue = [
            {
                "user_id": "tracked-user",
                "name": "Tracked User",
                "status": "pending",
                "invited_at": "2026-03-27T00:00:00+00:00",
            }
        ]

        def member_fetcher(user_id: str) -> dict:
            self.assertEqual(user_id, "tracked-user")
            return {"profile": {"name": "Tracked User"}, "party": {"_id": "another-party"}}

        reconcile_invite_queue(invite_queue, set(), set(), member_fetcher)

        self.assertEqual(invite_queue[0]["status"], "joined_other_party")

    def test_filter_invitable_candidates_skips_self_members_pending_and_duplicates(self) -> None:
        candidates = [
            {"id": "self-user", "name": "Self"},
            {"id": "member-user", "name": "Member"},
            {"id": "pending-user", "name": "Pending"},
            {"id": "fresh-user", "name": "Fresh"},
            {"id": "fresh-user", "name": "Fresh Duplicate"},
        ]

        result = filter_invitable_candidates(
            candidates,
            "self-user",
            {"member-user"},
            {"pending-user"},
        )

        self.assertEqual(result, [{"id": "fresh-user", "name": "Fresh"}])


if __name__ == "__main__":
    unittest.main()

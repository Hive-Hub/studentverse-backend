from __future__ import annotations

from datetime import timedelta
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from apps.communities.models import Community, CommunityMember, Channel

User = get_user_model()


class CommunityAPITests(APITestCase):
    def setUp(self):
        # Create test users
        self.owner_user = User.objects.create_user(username="owner", email="owner@example.com", password="Password123")
        self.admin_user = User.objects.create_user(username="admin_user", email="admin@example.com", password="Password123")
        self.mod_user = User.objects.create_user(username="mod_user", email="mod@example.com", password="Password123")
        self.member_user = User.objects.create_user(username="member_user", email="member@example.com", password="Password123")
        self.non_member_user = User.objects.create_user(username="non_member", email="non@example.com", password="Password123")

        # Set up a public community
        self.public_comm = Community.objects.create(
            name="Public Hackers",
            description="A public hacker community",
            is_public=True
        )
        # Assign members to public community
        CommunityMember.objects.create(community=self.public_comm, user=self.owner_user, role=CommunityMember.Role.OWNER)
        CommunityMember.objects.create(community=self.public_comm, user=self.admin_user, role=CommunityMember.Role.ADMIN)
        CommunityMember.objects.create(community=self.public_comm, user=self.mod_user, role=CommunityMember.Role.MODERATOR)
        CommunityMember.objects.create(community=self.public_comm, user=self.member_user, role=CommunityMember.Role.MEMBER)

        # Set up a private community
        self.private_comm = Community.objects.create(
            name="Private Cybers",
            description="A private cyber security community",
            is_public=False
        )
        # Assign owner to private community
        CommunityMember.objects.create(community=self.private_comm, user=self.owner_user, role=CommunityMember.Role.OWNER)

    # --- Utility methods for API Auth ---
    def authenticate_user(self, user):
        self.client.force_authenticate(user=user)

    # --- CRUD Tests ---

    def test_create_community(self):
        self.authenticate_user(self.owner_user)
        url = reverse("communities-list")
        data = {
            "name": "New Web Developers",
            "description": "Building the future web",
            "is_public": True,
            "rules": ["Be respectful", "No spam"]
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["success"], True)
        self.assertEqual(response.data["data"]["name"], "New Web Developers")
        self.assertEqual(response.data["data"]["user_role"], "owner")

        # Verify creator automatically became owner in CommunityMember relation
        new_comm = Community.objects.get(name="New Web Developers")
        membership = CommunityMember.objects.get(community=new_comm, user=self.owner_user)
        self.assertEqual(membership.role, CommunityMember.Role.OWNER)

    def test_list_communities_visibility(self):
        # 1. Anonymous user cannot list (requires authentication in ourViewSet permissions)
        url = reverse("communities-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Authenticated non-member sees only the public community
        self.authenticate_user(self.non_member_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Result contains 1 community
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(response.data["data"][0]["slug"], self.public_comm.slug)

        # 3. Private community owner sees the private community as well
        self.authenticate_user(self.owner_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Result contains 2 communities
        self.assertEqual(len(response.data["data"]), 2)

    def test_retrieve_community_access(self):
        # 1. Retrieve public community details (Allowed)
        self.authenticate_user(self.non_member_user)
        url = reverse("communities-detail", kwargs={"slug": self.public_comm.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["name"], self.public_comm.name)

        # 2. Non-member retrieve private community details (Denied)
        url_private = reverse("communities-detail", kwargs={"slug": self.private_comm.slug})
        response = self.client.get(url_private)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Private community owner retrieve details (Allowed)
        self.authenticate_user(self.owner_user)
        response = self.client.get(url_private)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_community_permissions(self):
        url = reverse("communities-detail", kwargs={"slug": self.public_comm.slug})
        data = {"description": "Updated Description"}

        # 1. Non-member update (Denied)
        self.authenticate_user(self.non_member_user)
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Moderator update (Denied)
        self.authenticate_user(self.mod_user)
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Admin update (Allowed)
        self.authenticate_user(self.admin_user)
        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["description"], "Updated Description")

        # 4. Owner update (Allowed)
        self.authenticate_user(self.owner_user)
        response = self.client.patch(url, {"description": "Owner update"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_delete_community_permissions(self):
        url = reverse("communities-detail", kwargs={"slug": self.public_comm.slug})

        # 1. Admin delete (Denied)
        self.authenticate_user(self.admin_user)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Owner delete (Allowed)
        self.authenticate_user(self.owner_user)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Community.objects.filter(pk=self.public_comm.pk).exists())

    # --- Membership, Join/Leave Flow Tests ---

    def test_join_public_community(self):
        self.authenticate_user(self.non_member_user)
        url = reverse("communities-join", kwargs={"slug": self.public_comm.slug})
        response = self.client.post(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["role"], "member")
        self.assertTrue(self.public_comm.memberships.filter(user=self.non_member_user).exists())

    def test_join_private_community(self):
        self.authenticate_user(self.non_member_user)
        url = reverse("communities-join", kwargs={"slug": self.private_comm.slug})

        # 1. Join without invite code (Failed)
        response = self.client.post(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # 2. Join with invalid invite code (Failed)
        response = self.client.post(url, {"invite_code": "BADCODE"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. Join with correct invite code (Success)
        correct_code = self.private_comm.invite_code
        response = self.client.post(url, {"invite_code": correct_code}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self.private_comm.memberships.filter(user=self.non_member_user).exists())

    def test_leave_community(self):
        # 1. Normal member leaving (Allowed)
        self.authenticate_user(self.member_user)
        url = reverse("communities-leave", kwargs={"slug": self.public_comm.slug})
        response = self.client.post(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(self.public_comm.memberships.filter(user=self.member_user).exists())

        # 2. Owner leaving (Denied)
        self.authenticate_user(self.owner_user)
        response = self.client.post(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invite_code_reset(self):
        self.authenticate_user(self.admin_user)
        old_code = self.public_comm.invite_code
        url = reverse("communities-invite-reset", kwargs={"slug": self.public_comm.slug})
        response = self.client.post(url, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify invite code changed
        self.public_comm.refresh_from_db()
        self.assertNotEqual(old_code, self.public_comm.invite_code)
        self.assertEqual(response.data["data"]["invite_code"], self.public_comm.invite_code)

    # --- Role Management & Promotion Tests ---

    def test_member_role_updates(self):
        # Get community membership ID for the mod user
        membership = self.public_comm.memberships.get(user=self.mod_user)
        url = reverse(
            "communities-members", 
            kwargs={"slug": self.public_comm.slug, "member_id": membership.id}
        )

        # 1. Non-member update role (Denied)
        self.authenticate_user(self.non_member_user)
        response = self.client.patch(url, {"role": "admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Admin promoting to Admin (Denied)
        self.authenticate_user(self.admin_user)
        response = self.client.patch(url, {"role": "admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Owner promoting to Admin (Allowed)
        self.authenticate_user(self.owner_user)
        response = self.client.patch(url, {"role": "admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        membership.refresh_from_db()
        self.assertEqual(membership.role, CommunityMember.Role.ADMIN)

    def test_transfer_ownership(self):
        self.authenticate_user(self.owner_user)
        url = reverse("communities-transfer-ownership", kwargs={"slug": self.public_comm.slug})
        
        # Transfer ownership to admin user
        response = self.client.post(url, {"target_user_id": self.admin_user.id}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify roles swapped
        owner_membership = self.public_comm.memberships.get(user=self.owner_user)
        admin_membership = self.public_comm.memberships.get(user=self.admin_user)

        self.assertEqual(owner_membership.role, CommunityMember.Role.ADMIN)
        self.assertEqual(admin_membership.role, CommunityMember.Role.OWNER)

    # --- Statistics Tests ---

    def test_community_statistics(self):
        self.authenticate_user(self.member_user)
        url = reverse("communities-statistics", kwargs={"slug": self.public_comm.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["members_count"], 4)
        self.assertEqual(response.data["data"]["role_distribution"]["owner"], 1)
        self.assertEqual(response.data["data"]["role_distribution"]["admin"], 1)
        self.assertEqual(response.data["data"]["role_distribution"]["moderator"], 1)
        self.assertEqual(response.data["data"]["role_distribution"]["member"], 1)
        self.assertEqual(response.data["data"]["joined_last_7_days"], 4)


class ChannelAPITests(APITestCase):
    def setUp(self):
        self.owner_user = User.objects.create_user(username="owner", email="owner@example.com", password="Password123")
        self.admin_user = User.objects.create_user(username="admin_user", email="admin@example.com", password="Password123")
        self.mod_user = User.objects.create_user(username="mod_user", email="mod@example.com", password="Password123")
        self.member_user = User.objects.create_user(username="member_user", email="member@example.com", password="Password123")
        self.non_member_user = User.objects.create_user(username="non_member", email="non@example.com", password="Password123")

        self.community = Community.objects.create(name="Hacker Server", is_public=True)
        CommunityMember.objects.create(community=self.community, user=self.owner_user, role=CommunityMember.Role.OWNER)
        CommunityMember.objects.create(community=self.community, user=self.admin_user, role=CommunityMember.Role.ADMIN)
        CommunityMember.objects.create(community=self.community, user=self.mod_user, role=CommunityMember.Role.MODERATOR)
        CommunityMember.objects.create(community=self.community, user=self.member_user, role=CommunityMember.Role.MEMBER)

        # Pre-create standard channels
        self.general_ch = Channel.objects.create(
            community=self.community,
            name="general",
            channel_type=Channel.ChannelType.GENERAL,
            permission_type=Channel.PermissionType.WRITE,
            order=2
        )
        self.rules_ch = Channel.objects.create(
            community=self.community,
            name="announcements",
            channel_type=Channel.ChannelType.ANNOUNCEMENTS,
            permission_type=Channel.PermissionType.READ_ONLY,
            is_pinned=True,
            order=1
        )
        self.mod_ch = Channel.objects.create(
            community=self.community,
            name="mod-chat",
            channel_type=Channel.ChannelType.GENERAL,
            permission_type=Channel.PermissionType.MODERATOR_ONLY,
            order=3
        )

    def authenticate_user(self, user):
        self.client.force_authenticate(user=user)

    def test_channel_creation_permissions(self):
        url = reverse("channels-list")
        
        # 1. Member cannot create (Forbidden)
        self.authenticate_user(self.member_user)
        response = self.client.post(url, {
            "community": self.community.slug,
            "name": "new-ch",
            "channel_type": "projects",
            "permission_type": "write"
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Admin can create (Success)
        self.authenticate_user(self.admin_user)
        response = self.client.post(url, {
            "community": self.community.slug,
            "name": "projects-hub",
            "channel_type": "projects",
            "permission_type": "write"
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["slug"], "projects-hub")

        # 3. Invalid name format validation error (starts with symbol)
        response = self.client.post(url, {
            "community": self.community.slug,
            "name": "-invalid-name",
            "channel_type": "projects"
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_channel_listing_and_visibility(self):
        url = reverse("channels-list")

        # 1. Non-member sees nothing (not part of the community)
        self.authenticate_user(self.non_member_user)
        response = self.client.get(f"{url}?community={self.community.slug}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 0)

        # 2. Standard member sees rules (pinned, announcements, read-only) and general (write), but NOT mod-chat (moderator_only)
        self.authenticate_user(self.member_user)
        response = self.client.get(f"{url}?community={self.community.slug}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 2)
        # Verify ordering: rules_ch is pinned=True, so it should be first
        self.assertEqual(response.data["data"][0]["id"], self.rules_ch.id)
        self.assertEqual(response.data["data"][1]["id"], self.general_ch.id)

        # 3. Moderator sees rules, general, AND mod-chat
        self.authenticate_user(self.mod_user)
        response = self.client.get(f"{url}?community={self.community.slug}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 3)

    def test_channel_write_permissions_can_write(self):
        # 1. Standard member: can_write in general (True), rules (False)
        self.authenticate_user(self.member_user)
        
        # General channel
        response_gen = self.client.get(reverse("channels-detail", kwargs={"pk": self.general_ch.id}))
        self.assertEqual(response_gen.status_code, status.HTTP_200_OK)
        self.assertEqual(response_gen.data["data"]["can_write"], True)

        # Rules channel (Read-Only)
        response_rules = self.client.get(reverse("channels-detail", kwargs={"pk": self.rules_ch.id}))
        self.assertEqual(response_rules.status_code, status.HTTP_200_OK)
        self.assertEqual(response_rules.data["data"]["can_write"], False)

        # 2. Moderator: can_write in general (True), rules (True), mod-chat (True)
        self.authenticate_user(self.mod_user)
        for ch_id in [self.general_ch.id, self.rules_ch.id, self.mod_ch.id]:
            response = self.client.get(reverse("channels-detail", kwargs={"pk": ch_id}))
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["data"]["can_write"], True)

    def test_channel_update_and_delete(self):
        url = reverse("channels-detail", kwargs={"pk": self.general_ch.id})

        # 1. Moderator update name (Forbidden - only Admin/Owner can update channel configuration)
        self.authenticate_user(self.mod_user)
        response = self.client.patch(url, {"name": "general-updated"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Admin update name (Success)
        self.authenticate_user(self.admin_user)
        response = self.client.patch(url, {"name": "lounge"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["name"], "lounge")

        # 3. Member delete channel (Forbidden)
        self.authenticate_user(self.member_user)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 4. Owner delete channel (Success)
        self.authenticate_user(self.owner_user)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Channel.objects.filter(pk=self.general_ch.pk).exists())


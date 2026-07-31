from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.communities.models import Community, CommunityMember, Channel
from apps.messaging.models import Message, MessageAttachment, MessageReaction

User = get_user_model()


class MessagingAPITests(APITestCase):
    def setUp(self):
        # Users
        self.owner = User.objects.create_user(username="msg_owner", email="msg_owner@x.com", password="Pass1234")
        self.admin = User.objects.create_user(username="msg_admin", email="msg_admin@x.com", password="Pass1234")
        self.mod = User.objects.create_user(username="msg_mod", email="msg_mod@x.com", password="Pass1234")
        self.member = User.objects.create_user(username="msg_member", email="msg_member@x.com", password="Pass1234")
        self.outsider = User.objects.create_user(username="msg_out", email="msg_out@x.com", password="Pass1234")

        # Community & memberships
        self.community = Community.objects.create(name="Msg Community", is_public=True)
        CommunityMember.objects.create(community=self.community, user=self.owner, role=CommunityMember.Role.OWNER)
        CommunityMember.objects.create(community=self.community, user=self.admin, role=CommunityMember.Role.ADMIN)
        CommunityMember.objects.create(community=self.community, user=self.mod, role=CommunityMember.Role.MODERATOR)
        CommunityMember.objects.create(community=self.community, user=self.member, role=CommunityMember.Role.MEMBER)

        # Channels
        self.write_channel = Channel.objects.create(
            community=self.community, name="general", channel_type="general",
            permission_type=Channel.PermissionType.WRITE
        )
        self.read_only_channel = Channel.objects.create(
            community=self.community, name="announcements", channel_type="announcements",
            permission_type=Channel.PermissionType.READ_ONLY
        )

        # Pre-created messages
        self.msg1 = Message.objects.create(channel=self.write_channel, author=self.member, content="Hello world")
        self.msg2 = Message.objects.create(channel=self.write_channel, author=self.owner, content="Owner message")

    def auth(self, user):
        self.client.force_authenticate(user=user)

    # --- List ---

    def test_list_messages_member_can_read(self):
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]), 2)

    def test_list_messages_outsider_blocked(self):
        self.auth(self.outsider)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_search_messages(self):
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/?search=Hello"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]), 1)
        self.assertIn("Hello", resp.data["data"][0]["content"])

    # --- Send ---

    def test_send_message_member_write_channel(self):
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/"
        resp = self.client.post(url, {"content": "New message from member"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["data"]["content"], "New message from member")

    def test_send_message_member_read_only_channel_blocked(self):
        self.auth(self.member)
        url = f"/api/v1/channels/{self.read_only_channel.id}/messages/"
        resp = self.client.post(url, {"content": "Should fail"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_send_message_mod_read_only_channel_ok(self):
        self.auth(self.mod)
        url = f"/api/v1/channels/{self.read_only_channel.id}/messages/"
        resp = self.client.post(url, {"content": "Mod announcement"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_send_empty_message_fails(self):
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/"
        resp = self.client.post(url, {"content": ""}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # --- Thread Reply ---

    def test_send_thread_reply(self):
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/"
        resp = self.client.post(url, {"content": "Reply!", "parent_id": self.msg1.id}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["data"]["parent_id"], self.msg1.id)

    def test_get_thread_replies(self):
        reply = Message.objects.create(channel=self.write_channel, author=self.member, content="Reply", parent=self.msg1)
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/{self.msg1.id}/thread/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]), 1)
        self.assertEqual(resp.data["data"][0]["id"], reply.id)

    # --- Edit ---

    def test_edit_own_message(self):
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/{self.msg1.id}/"
        resp = self.client.patch(url, {"content": "Edited content"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["data"]["is_edited"])
        self.assertEqual(resp.data["data"]["content"], "Edited content")

    def test_edit_other_message_blocked(self):
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/{self.msg2.id}/"
        resp = self.client.patch(url, {"content": "Hack"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # --- Delete ---

    def test_delete_own_message(self):
        msg = Message.objects.create(channel=self.write_channel, author=self.member, content="to delete")
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/{msg.id}/"
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(Message.objects.filter(pk=msg.id).exists())

    def test_delete_other_message_as_member_blocked(self):
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/{self.msg2.id}/"
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_any_message_as_admin(self):
        self.auth(self.admin)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/{self.msg1.id}/"
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # --- Reactions ---

    def test_add_reaction(self):
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/{self.msg1.id}/react/"
        resp = self.client.post(url, {"emoji": "👍"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_duplicate_reaction_blocked(self):
        MessageReaction.objects.create(message=self.msg1, user=self.member, emoji="👍")
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/{self.msg1.id}/react/"
        resp = self.client.post(url, {"emoji": "👍"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_remove_reaction(self):
        MessageReaction.objects.create(message=self.msg1, user=self.member, emoji="❤️")
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/{self.msg1.id}/react/"
        resp = self.client.delete(url, {"emoji": "❤️"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(MessageReaction.objects.filter(message=self.msg1, user=self.member, emoji="❤️").exists())

    def test_reaction_grouped_in_response(self):
        MessageReaction.objects.create(message=self.msg1, user=self.member, emoji="👍")
        MessageReaction.objects.create(message=self.msg1, user=self.owner, emoji="👍")
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/{self.msg1.id}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        reactions = resp.data["data"]["reactions"]
        thumbs_up = next((r for r in reactions if r["emoji"] == "👍"), None)
        self.assertIsNotNone(thumbs_up)
        self.assertEqual(thumbs_up["count"], 2)
        self.assertTrue(thumbs_up["reacted_by_me"])

    # --- Pin ---

    def test_pin_by_mod(self):
        self.auth(self.mod)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/{self.msg1.id}/pin/"
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["data"]["is_pinned"])

    def test_pin_by_member_blocked(self):
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/{self.msg1.id}/pin/"
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_pinned_only_filter(self):
        self.msg1.is_pinned = True
        self.msg1.save()
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/?pinned_only=true"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]), 1)
        self.assertEqual(resp.data["data"][0]["id"], self.msg1.id)

    # --- can_edit / can_delete flags ---

    def test_can_edit_flag(self):
        self.auth(self.member)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/{self.msg1.id}/"
        resp = self.client.get(url)
        self.assertTrue(resp.data["data"]["can_edit"])

    def test_can_delete_flag_for_admin(self):
        self.auth(self.admin)
        url = f"/api/v1/channels/{self.write_channel.id}/messages/{self.msg1.id}/"
        resp = self.client.get(url)
        self.assertTrue(resp.data["data"]["can_delete"])

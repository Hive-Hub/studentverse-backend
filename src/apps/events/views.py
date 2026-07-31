from __future__ import annotations

import uuid
import django.utils.timezone as timezone
from django.db import models
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.responses import success_response, error_response
from apps.communities.models import Community, CommunityMember
from .models import Event, EventSpeaker, EventSponsor, EventGalleryImage, EventRSVP, EventReminder, EventComment
from .permissions import IsEventAuthorOrModeratorOrReadOnly, IsEventCommentAuthorOrModeratorOrReadOnly
from .serializers import (
    EventSerializer,
    EventCreateUpdateSerializer,
    EventRSVPSerializer,
    EventCommentSerializer,
    EventSpeakerSerializer,
    EventSponsorSerializer,
    EventGalleryImageSerializer,
)


class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsEventAuthorOrModeratorOrReadOnly]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return EventCreateUpdateSerializer
        return EventSerializer

    def get_queryset(self):
        user = self.request.user
        if not user or user.is_anonymous:
            return Event.objects.none()

        user_profile = getattr(user, "profile", None)
        user_role = user_profile.role if user_profile else "student"

        # Base queryset optimization
        queryset = Event.objects.select_related(
            "author", "author__profile", "community"
        ).prefetch_related("speakers", "sponsors", "gallery")

        # Platform Admin and Moderator can see everything (including blocked)
        if user_role in ["admin", "moderator"]:
            # Apply query param filtering even for admins
            pass
        else:
            # Hide blocked events
            queryset = queryset.filter(is_blocked=False)

            # Filter private community events
            user_communities = user.community_memberships.values_list("community_id", flat=True)
            queryset = queryset.filter(
                ~Q(scope=Event.Scope.COMMUNITY) |
                Q(community__is_public=True) |
                Q(community__in=user_communities)
            )

            # Filter college events
            if user_profile and user_profile.college:
                queryset = queryset.filter(
                    ~Q(scope=Event.Scope.COLLEGE) |
                    Q(college__iexact=user_profile.college)
                )
            else:
                queryset = queryset.filter(~Q(scope=Event.Scope.COLLEGE))

        # Query param filters
        scope = self.request.query_params.get("scope")
        if scope:
            queryset = queryset.filter(scope=scope)

        event_type = self.request.query_params.get("event_type")
        if event_type:
            queryset = queryset.filter(event_type=event_type)

        college = self.request.query_params.get("college")
        if college:
            queryset = queryset.filter(college__iexact=college)

        community = self.request.query_params.get("community")
        if community:
            if str(community).isdigit():
                queryset = queryset.filter(community_id=community)
            else:
                queryset = queryset.filter(community__slug=community)

        # Search filter
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )

        return queryset

    def perform_create(self, serializer) -> None:
        serializer.save(author=self.request.user)

    # --- Response Envelope Overrides ---

    def create(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return success_response(
            message="Event created successfully.",
            data=serializer.data,
            status_code=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs) -> Response:
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return success_response(
            message="Event updated successfully.", data=serializer.data
        )

    def destroy(self, request, *args, **kwargs) -> Response:
        instance = self.get_object()
        self.perform_destroy(instance)
        return success_response(
            message="Event deleted successfully.",
            status_code=status.HTTP_200_OK,
        )

    def retrieve(self, request, *args, **kwargs) -> Response:
        instance = self.get_object()
        
        # Log recently visited
        from apps.search.services import log_visited_entity
        log_visited_entity(request.user, "event", instance.id, instance.title)
        
        serializer = self.get_serializer(instance)
        return success_response(message="Event retrieved.", data=serializer.data)

    def list(self, request, *args, **kwargs) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(message="Event list retrieved.", data=serializer.data)

    # --- RSVP Actions (Join, Leave) ---

    @action(detail=True, methods=["post"])
    def join(self, request, pk=None) -> Response:
        """Join an event, placing the user on the waitlist if seats are fully filled."""
        event = self.get_object()
        
        # Check if already joined
        rsvp_qs = EventRSVP.objects.filter(event=event, user=request.user)
        if rsvp_qs.exists():
            rsvp = rsvp_qs.first()
            return error_response(
                message=f"You have already RSVP'd to this event. Status: {rsvp.get_status_display()}.",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Capacity check
        status_assigned = EventRSVP.Status.JOINED
        if event.seats is not None:
            current_joined = EventRSVP.objects.filter(event=event, status=EventRSVP.Status.JOINED).count()
            if current_joined >= event.seats:
                status_assigned = EventRSVP.Status.WAITING_LIST

        rsvp = EventRSVP.objects.create(
            event=event,
            user=request.user,
            status=status_assigned
        )

        # Notify event author of new RSVP
        if event.author != request.user:
            from apps.notifications.services import create_notification
            create_notification(
                recipient=event.author,
                notification_type="event",
                title="New Event RSVP",
                content=f"{request.user.username} RSVP'd to {event.title}.",
                data={"event_id": event.id, "rsvp_status": rsvp.status}
            )

        message = "Joined event successfully." if status_assigned == EventRSVP.Status.JOINED else "Event is full. Added to waiting list."
        serializer = EventRSVPSerializer(rsvp, context={"request": request})
        return success_response(message=message, data=serializer.data)

    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None) -> Response:
        """Leave an event, promoting the oldest waitlisted user to joined status."""
        event = self.get_object()
        
        rsvp_qs = EventRSVP.objects.filter(event=event, user=request.user)
        if not rsvp_qs.exists():
            return error_response(
                message="You have not RSVP'd to this event.",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        rsvp = rsvp_qs.first()
        old_status = rsvp.status
        rsvp.delete()

        # Promotion check: if a confirmed seat was freed, promote the oldest waitlisted user
        if old_status == EventRSVP.Status.JOINED and event.seats is not None:
            oldest_waitlist = EventRSVP.objects.filter(
                event=event, status=EventRSVP.Status.WAITING_LIST
            ).order_by("joined_at").first()
            
            if oldest_waitlist:
                oldest_waitlist.status = EventRSVP.Status.JOINED
                oldest_waitlist.save(update_fields=["status"])

        return success_response(message="Left event successfully.")

    # --- Attendance Check-in ---

    @action(detail=True, methods=["post"], url_path="check-in")
    def check_in(self, request, pk=None) -> Response:
        """Mark user attendance using the event's QR Code key."""
        event = self.get_object()
        qr_key = request.data.get("qr_code_key")
        
        if not qr_key:
            return error_response(message="QR Code Key is required.", status_code=status.HTTP_400_BAD_REQUEST)

        # Validate QR Key matches
        if str(event.qr_code_key) != str(qr_key):
            return error_response(message="Invalid QR Code Key.", status_code=status.HTTP_400_BAD_REQUEST)

        # Find RSVP
        rsvp = EventRSVP.objects.filter(event=event, user=request.user).first()
        if not rsvp:
            return error_response(message="You have not registered for this event.", status_code=status.HTTP_400_BAD_REQUEST)

        if rsvp.status == EventRSVP.Status.WAITING_LIST:
            return error_response(message="Cannot check-in from the waiting list.", status_code=status.HTTP_400_BAD_REQUEST)

        rsvp.attended = True
        rsvp.save(update_fields=["attended"])

        # Notify event author of check-in
        if event.author != request.user:
            from apps.notifications.services import create_notification
            create_notification(
                recipient=event.author,
                notification_type="event",
                title="Event Check-in",
                content=f"{request.user.username} checked into {event.title}.",
                data={"event_id": event.id}
            )
        
        serializer = EventRSVPSerializer(rsvp, context={"request": request})
        return success_response(message="Checked in successfully.", data=serializer.data)

    # --- Reminders ---

    @action(detail=True, methods=["post"])
    def remind(self, request, pk=None) -> Response:
        """Configure a calendar reminder for an event."""
        event = self.get_object()
        reminder_time_str = request.data.get("reminder_time")
        
        if not reminder_time_str:
            return error_response(message="reminder_time is required.", status_code=status.HTTP_400_BAD_REQUEST)

        try:
            reminder_time = timezone.datetime.fromisoformat(reminder_time_str.replace("Z", "+00:00"))
        except ValueError:
            return error_response(message="Invalid ISO datetime format for reminder_time.", status_code=status.HTTP_400_BAD_REQUEST)

        # Verify reminder is in the future
        if reminder_time <= timezone.now():
            return error_response(message="Reminder time must be in the future.", status_code=status.HTTP_400_BAD_REQUEST)

        reminder, created = EventReminder.objects.update_or_create(
            event=event,
            user=request.user,
            defaults={"reminder_time": reminder_time, "sent": False}
        )

        return success_response(message="Reminder scheduled successfully.")

    # --- iCalendar Export (.ics) ---

    @action(detail=True, methods=["get"])
    def ical(self, request, pk=None) -> HttpResponse:
        """Export event to iCalendar format (.ics)."""
        event = self.get_object()
        
        dtstamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
        dtstart = event.start_time.strftime("%Y%m%dT%H%M%SZ")
        dtend = event.end_time.strftime("%Y%m%dT%H%M%SZ")
        
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//StudentVerse//Events//EN",
            "BEGIN:VEVENT",
            f"UID:event-{event.id}@studentverse.com",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"SUMMARY:{event.title}",
            f"DESCRIPTION:{event.description}",
            f"LOCATION:{event.location or event.event_type}",
            "END:VEVENT",
            "END:VCALENDAR",
        ]
        
        ics_content = "\r\n".join(lines)
        response = HttpResponse(ics_content, content_type="text/calendar")
        response["Content-Disposition"] = f'attachment; filename="event-{event.id}.ics"'
        return response

    # --- Comments ---

    @action(detail=True, methods=["get", "post"], url_path="comments")
    def comments(self, request, pk=None) -> Response:
        event = self.get_object()
        if request.method == "GET":
            comments = EventComment.objects.filter(event=event, parent__isnull=True).select_related("user", "user__profile")
            serializer = EventCommentSerializer(comments, many=True, context={"request": request})
            return success_response(message="Comments retrieved.", data=serializer.data)
            
        elif request.method == "POST":
            content = request.data.get("content", "").strip()
            if not content:
                return error_response(message="Content is required.", status_code=status.HTTP_400_BAD_REQUEST)
                
            parent_id = request.data.get("parent")
            parent = None
            if parent_id:
                parent = get_object_or_404(EventComment, id=parent_id, event=event)
                
            comment = EventComment.objects.create(
                event=event,
                user=request.user,
                content=content,
                parent=parent
            )

            # Send Notification Center notifications
            from apps.notifications.services import create_notification
            if event.author != request.user:
                create_notification(
                    recipient=event.author,
                    notification_type="event",
                    title="New comment on your event",
                    content=f"{request.user.username} commented: {content[:30]}...",
                    data={"event_id": event.id, "comment_id": comment.id}
                )
            if parent and parent.user != request.user:
                create_notification(
                    recipient=parent.user,
                    notification_type="reply",
                    title="Reply to your event comment",
                    content=f"{request.user.username} replied: {content[:30]}...",
                    data={"event_id": event.id, "comment_id": comment.id, "parent_comment_id": parent.id}
                )

            serializer = EventCommentSerializer(comment, context={"request": request})
            return success_response(
                message="Comment created successfully.",
                data=serializer.data,
                status_code=status.HTTP_201_CREATED
            )

    # --- Gallery ---

    @action(detail=True, methods=["post"], url_path="gallery")
    def gallery(self, request, pk=None) -> Response:
        event = self.get_object()
        images = request.FILES.getlist("images")
        if not images:
            return error_response(message="No images provided.", status_code=status.HTTP_400_BAD_REQUEST)
            
        uploaded_images = []
        for img in images:
            gallery_img = EventGalleryImage.objects.create(
                event=event,
                image=img
            )
            uploaded_images.append(gallery_img)
            
        serializer = EventGalleryImageSerializer(uploaded_images, many=True)
        return success_response(
            message=f"{len(uploaded_images)} image(s) uploaded to gallery.",
            data=serializer.data,
            status_code=status.HTTP_201_CREATED
        )

    # --- Speaker Management ---

    @action(detail=True, methods=["post"], url_path="speakers")
    def add_speaker(self, request, pk=None) -> Response:
        event = self.get_object()
        name = request.data.get("name", "").strip()
        bio = request.data.get("bio", "").strip()
        photo = request.FILES.get("photo")
        
        if not name:
            return error_response(message="Speaker name is required.", status_code=status.HTTP_400_BAD_REQUEST)

        speaker = EventSpeaker.objects.create(
            event=event,
            name=name,
            bio=bio,
            photo=photo
        )
        serializer = EventSpeakerSerializer(speaker)
        return success_response(
            message="Speaker added successfully.",
            data=serializer.data,
            status_code=status.HTTP_201_CREATED
        )

    # --- Sponsor Management ---

    @action(detail=True, methods=["post"], url_path="sponsors")
    def add_sponsor(self, request, pk=None) -> Response:
        event = self.get_object()
        name = request.data.get("name", "").strip()
        logo = request.FILES.get("logo")
        website = request.data.get("website", "").strip()
        
        if not name:
            return error_response(message="Sponsor name is required.", status_code=status.HTTP_400_BAD_REQUEST)

        sponsor = EventSponsor.objects.create(
            event=event,
            name=name,
            logo=logo,
            website=website or None
        )
        serializer = EventSponsorSerializer(sponsor)
        sponsor_data = serializer.data
        return success_response(
            message="Sponsor added successfully.",
            data=sponsor_data,
            status_code=status.HTTP_201_CREATED
        )


class EventCommentViewSet(viewsets.GenericViewSet):
    queryset = EventComment.objects.all()
    serializer_class = EventCommentSerializer
    permission_classes = [permissions.IsAuthenticated, IsEventCommentAuthorOrModeratorOrReadOnly]

    def destroy(self, request, pk=None) -> Response:
        comment = get_object_or_404(EventComment, id=pk)
        self.check_object_permissions(request, comment)
        comment.delete()
        return success_response(message="Comment deleted.")

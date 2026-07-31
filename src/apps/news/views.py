from __future__ import annotations

import django.utils.timezone as timezone
from django.db import models
from django.db.models import Count, Q, F, Sum, Case, When, Value, IntegerField
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.responses import success_response, error_response
from apps.communities.models import Community, CommunityMember
from .models import Tag, News, NewsLike, NewsBookmark, NewsReport, NewsComment, NewsAttachment
from .permissions import IsNewsAuthorOrModeratorOrReadOnly, IsCommentAuthorOrModeratorOrReadOnly
from .serializers import (
    TagSerializer,
    NewsSerializer,
    NewsCreateUpdateSerializer,
    NewsCommentSerializer,
    NewsReportSerializer,
    NewsAttachmentSerializer,
)
from .websocket import broadcast_news_published


class NewsViewSet(viewsets.ModelViewSet):
    queryset = News.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsNewsAuthorOrModeratorOrReadOnly]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return NewsCreateUpdateSerializer
        return NewsSerializer

    def get_queryset(self):
        user = self.request.user
        if not user or user.is_anonymous:
            return News.objects.none()

        user_profile = getattr(user, "profile", None)
        user_role = user_profile.role if user_profile else "student"

        # Baseline queryset with select_related / prefetch_related for performance
        queryset = News.objects.select_related(
            "author", "author__profile", "community"
        ).prefetch_related("tags", "attachments")

        # Platform Admin and Platform Moderator can view all items (including drafts and blocked)
        if user_role in ["admin", "moderator"]:
            return queryset

        # Hide blocked news
        queryset = queryset.filter(is_blocked=False)

        # Standard users can see published news (scheduled publish time passed) OR their own drafts
        now = timezone.now()
        queryset = queryset.filter(
            Q(status=News.Status.PUBLISHED, scheduled_publish_at__isnull=True) |
            Q(status=News.Status.PUBLISHED, scheduled_publish_at__lte=now) |
            Q(author=user)
        )

        # Filter private community news
        user_communities = user.community_memberships.values_list("community_id", flat=True)
        queryset = queryset.filter(
            ~Q(scope=News.Scope.COMMUNITY) |
            Q(community__is_public=True) |
            Q(community__in=user_communities)
        )

        # Filter college news
        if user_profile and user_profile.college:
            queryset = queryset.filter(
                ~Q(scope=News.Scope.COLLEGE) |
                Q(college__iexact=user_profile.college)
            )
        else:
            queryset = queryset.filter(~Q(scope=News.Scope.COLLEGE))

        return queryset

    def create(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return success_response(
            message="News article created successfully.",
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
            message="News article updated successfully.", data=serializer.data
        )

    def destroy(self, request, *args, **kwargs) -> Response:
        instance = self.get_object()
        self.perform_destroy(instance)
        return success_response(
            message="News article deleted successfully.",
            status_code=status.HTTP_200_OK,
        )

    def retrieve(self, request, *args, **kwargs) -> Response:
        instance = self.get_object()
        # Increment views count
        instance.views_count += 1
        instance.save(update_fields=["views_count"])
        
        # Log recently visited
        from apps.search.services import log_visited_entity
        log_visited_entity(request.user, "news", instance.id, instance.title)
        
        serializer = self.get_serializer(instance)
        return success_response(message="News article retrieved.", data=serializer.data)

    def list(self, request, *args, **kwargs) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(message="News list retrieved.", data=serializer.data)

    def _check_and_broadcast_publish(self, news: News) -> None:
        now = timezone.now()
        is_active_published = (
            news.status == News.Status.PUBLISHED and
            (not news.scheduled_publish_at or news.scheduled_publish_at <= now) and
            not news.is_blocked
        )
        if is_active_published:
            serializer = NewsSerializer(news, context={"request": self.request})
            broadcast_news_published(serializer.data)

            # Send Notification Center updates to recipients
            from apps.notifications.services import create_notification
            from django.contrib.auth import get_user_model

            User = get_user_model()
            if news.scope == News.Scope.COMMUNITY and news.community:
                recipients = User.objects.filter(community_memberships__community=news.community).exclude(id=news.author.id)
            elif news.scope == News.Scope.COLLEGE and news.college:
                recipients = User.objects.filter(profile__college__iexact=news.college).exclude(id=news.author.id)
            else:
                recipients = User.objects.all().exclude(id=news.author.id)

            for recipient in list(recipients):
                create_notification(
                    recipient=recipient,
                    notification_type="news",
                    title=f"New article: {news.title}",
                    content=f"{news.author.username} published a new article.",
                    data={
                        "news_id": news.id,
                        "community_id": news.community.id if news.community else None,
                    },
                )

    def perform_create(self, serializer) -> None:
        news = serializer.save(author=self.request.user)
        self._check_and_broadcast_publish(news)

    def perform_update(self, serializer) -> None:
        old_instance = self.get_object()
        old_status = old_instance.status
        old_scheduled = old_instance.scheduled_publish_at

        news = serializer.save()

        was_published = (
            old_status == News.Status.PUBLISHED and
            (not old_scheduled or old_scheduled <= timezone.now())
        )
        if not was_published:
            self._check_and_broadcast_publish(news)

    # --- News Action Endpoints ---

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None) -> Response:
        """Explicitly transition draft news to published status immediately."""
        news = self.get_object()
        if news.status == News.Status.PUBLISHED and (not news.scheduled_publish_at or news.scheduled_publish_at <= timezone.now()):
            return error_response(message="News is already published.", status_code=status.HTTP_400_BAD_REQUEST)
        
        news.status = News.Status.PUBLISHED
        news.scheduled_publish_at = None
        news.save(update_fields=["status", "scheduled_publish_at"])
        self._check_and_broadcast_publish(news)
        
        serializer = NewsSerializer(news, context={"request": request})
        return success_response(message="News article published.", data=serializer.data)

    @action(detail=True, methods=["post"])
    def like(self, request, pk=None) -> Response:
        """Toggle like status on a news article."""
        news = self.get_object()
        like_qs = NewsLike.objects.filter(user=request.user, news=news)
        if like_qs.exists():
            like_qs.delete()
            return success_response(message="Liked removed.", data={"is_liked": False})
        
        NewsLike.objects.create(user=request.user, news=news)
        return success_response(message="Liked successfully.", data={"is_liked": True})

    @action(detail=True, methods=["post"])
    def bookmark(self, request, pk=None) -> Response:
        """Toggle bookmark status on a news article."""
        news = self.get_object()
        bookmark_qs = NewsBookmark.objects.filter(user=request.user, news=news)
        if bookmark_qs.exists():
            bookmark_qs.delete()
            return success_response(message="Bookmark removed.", data={"is_bookmarked": False})
        
        NewsBookmark.objects.create(user=request.user, news=news)
        return success_response(message="Bookmarked successfully.", data={"is_bookmarked": True})

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None) -> Response:
        """Track and increment shares, returning a share link."""
        news = self.get_object()
        news.shares_count += 1
        news.save(update_fields=["shares_count"])
        
        # Build dummy client share link
        share_url = f"/news/{news.id}"
        return success_response(
            message="News article shared.",
            data={
                "shares_count": news.shares_count,
                "share_url": share_url
            }
        )

    @action(detail=True, methods=["post"])
    def report(self, request, pk=None) -> Response:
        """Report news for inappropriate content."""
        news = self.get_object()
        reason = request.data.get("reason", "").strip()
        if not reason:
            return error_response(message="Reason is required.", status_code=status.HTTP_400_BAD_REQUEST)
        
        report, created = NewsReport.objects.get_or_create(
            user=request.user,
            news=news,
            defaults={"reason": reason}
        )
        if not created:
            report.reason = reason
            report.save(update_fields=["reason"])
            
        return success_response(message="News article reported successfully.")

    # --- Comments ---

    @action(detail=True, methods=["get", "post"], url_path="comments")
    def comments(self, request, pk=None) -> Response:
        news = self.get_object()
        if request.method == "GET":
            # List only top-level comments; replies are serialized inline
            comments = NewsComment.objects.filter(news=news, parent__isnull=True).select_related("user", "user__profile")
            serializer = NewsCommentSerializer(comments, many=True, context={"request": request})
            return success_response(message="Comments retrieved.", data=serializer.data)
            
        elif request.method == "POST":
            content = request.data.get("content", "").strip()
            if not content:
                return error_response(message="Content is required.", status_code=status.HTTP_400_BAD_REQUEST)
                
            parent_id = request.data.get("parent")
            parent = None
            if parent_id:
                parent = get_object_or_404(NewsComment, id=parent_id, news=news)
                
            comment = NewsComment.objects.create(
                news=news,
                user=request.user,
                content=content,
                parent=parent
            )

            # Send Notification Center notifications
            from apps.notifications.services import create_notification
            if news.author != request.user:
                create_notification(
                    recipient=news.author,
                    notification_type="reply",
                    title="New comment on your article",
                    content=f"{request.user.username} commented: {content[:30]}...",
                    data={"news_id": news.id, "comment_id": comment.id}
                )
            if parent and parent.user != request.user:
                create_notification(
                    recipient=parent.user,
                    notification_type="reply",
                    title="Reply to your comment",
                    content=f"{request.user.username} replied: {content[:30]}...",
                    data={"news_id": news.id, "comment_id": comment.id, "parent_comment_id": parent.id}
                )

            serializer = NewsCommentSerializer(comment, context={"request": request})
            return success_response(
                message="Comment created successfully.",
                data=serializer.data,
                status_code=status.HTTP_201_CREATED
            )

    # --- Attachments ---

    @action(detail=True, methods=["post"], url_path="attachments")
    def attachments(self, request, pk=None) -> Response:
        news = self.get_object()
        files = request.FILES.getlist("files")
        if not files:
            return error_response(message="No files provided.", status_code=status.HTTP_400_BAD_REQUEST)
            
        if len(files) > 10:
            return error_response(message="Cannot upload more than 10 files.", status_code=status.HTTP_400_BAD_REQUEST)
            
        uploaded_attachments = []
        for file in files:
            # 25MB check
            if file.size > 25 * 1024 * 1024:
                return error_response(
                    message=f"File {file.name} exceeds maximum allowed size of 25MB.",
                    status_code=status.HTTP_400_BAD_REQUEST
                )
                
            attachment = NewsAttachment.objects.create(
                news=news,
                file=file,
                file_name=file.name,
                file_size=file.size,
                mime_type=getattr(file, "content_type", "application/octet-stream")
            )
            uploaded_attachments.append(attachment)
            
        serializer = NewsAttachmentSerializer(uploaded_attachments, many=True)
        return success_response(
            message=f"{len(uploaded_attachments)} file(s) attached.",
            data=serializer.data,
            status_code=status.HTTP_201_CREATED
        )

    # --- Feeds ---

    @action(detail=False, methods=["get"])
    def latest(self, request) -> Response:
        """Latest news feed."""
        queryset = self.filter_queryset(self.get_queryset()).order_by("-is_pinned", "-created_at")
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(queryset, many=True)
        return success_response(message="Latest news feed retrieved.", data=serializer.data)

    @action(detail=False, methods=["get"])
    def trending(self, request) -> Response:
        """Trending news feed based on activity metrics."""
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.annotate(
            likes_count_annotated=Count("likes", distinct=True),
            comments_count_annotated=Count("comments", distinct=True),
        )
        
        # Scoring: likes * 3 + comments * 2 + shares + views
        queryset = queryset.annotate(
            trending_score=(F("likes_count_annotated") * 3) +
                           (F("comments_count_annotated") * 2) +
                           F("shares_count") +
                           F("views_count")
        ).order_by("-is_pinned", "-trending_score", "-created_at")
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(queryset, many=True)
        return success_response(message="Trending news feed retrieved.", data=serializer.data)

    @action(detail=False, methods=["get"])
    def recommended(self, request) -> Response:
        """Recommended news feed based on user interests, college, and communities."""
        user = request.user
        user_profile = getattr(user, "profile", None)
        interests = user_profile.interests if user_profile else []
        college = user_profile.college if user_profile else ""
        user_communities = list(user.community_memberships.values_list("community_id", flat=True)) if user else []

        queryset = self.filter_queryset(self.get_queryset())
        
        match_conditions = []
        if interests:
            interests_lower = [i.strip().lower() for i in interests]
            # Match news category with interest
            match_conditions.append(When(category__in=interests_lower, then=Value(5)))
            # Match news tags with interest
            match_conditions.append(When(tags__name__in=interests_lower, then=Value(3)))
        if college:
            match_conditions.append(When(college__iexact=college, then=Value(10)))
        if user_communities:
            match_conditions.append(When(community__in=user_communities, then=Value(10)))

        if match_conditions:
            # We useSum(Case(...)) to aggregate total recommendation points for each news article
            queryset = queryset.annotate(
                rec_score=Sum(
                    Case(
                        *match_conditions,
                        default=Value(0),
                        output_field=IntegerField()
                    )
                )
            ).order_by("-is_pinned", "-rec_score", "-created_at")
        else:
            queryset = queryset.order_by("-is_pinned", "-created_at")

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(queryset, many=True)
        return success_response(message="Recommended news feed retrieved.", data=serializer.data)

    @action(detail=False, methods=["get"])
    def college(self, request) -> Response:
        """College specific news feed."""
        user_profile = getattr(request.user, "profile", None)
        college = user_profile.college if user_profile else ""
        if not college:
            return success_response(message="No college set on profile.", data=[])
            
        queryset = self.filter_queryset(self.get_queryset()).filter(
            scope=News.Scope.COLLEGE,
            college__iexact=college
        )
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(queryset, many=True)
        return success_response(message="College news feed retrieved.", data=serializer.data)

    @action(detail=False, methods=["get"], url_path="community/(?P<community_id>[^/.]+)")
    def community_feed(self, request, community_id=None) -> Response:
        """Community specific news feed."""
        # Find community
        try:
            if str(community_id).isdigit():
                community = Community.objects.get(pk=community_id)
            else:
                community = Community.objects.get(slug=community_id)
        except Community.DoesNotExist:
            return error_response(message="Community not found.", status_code=status.HTTP_404_NOT_FOUND)
            
        # Check permissions: if private community, user must be member
        if not community.is_public and not community.memberships.filter(user=request.user).exists():
            return error_response(message="You do not have access to this community's news.", status_code=status.HTTP_403_FORBIDDEN)
            
        queryset = self.filter_queryset(self.get_queryset()).filter(
            scope=News.Scope.COMMUNITY,
            community=community
        )
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(queryset, many=True)
        return success_response(message="Community news feed retrieved.", data=serializer.data)

    # --- Admin Moderation Endpoints ---

    @action(detail=False, methods=["get"], url_path="moderation")
    def moderation_queue(self, request) -> Response:
        """List reported news articles. Platform admins/moderators only."""
        user_profile = getattr(request.user, "profile", None)
        user_role = user_profile.role if user_profile else "student"
        if user_role not in ["admin", "moderator"]:
            return error_response(message="Moderation queue requires staff role.", status_code=status.HTTP_403_FORBIDDEN)
            
        # Filter news with at least one report
        queryset = News.objects.annotate(reports_count=Count("reports")).filter(reports_count__gt=0).order_by("-reports_count", "-created_at")
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(queryset, many=True)
        return success_response(message="Moderation queue retrieved.", data=serializer.data)

    @action(detail=True, methods=["post"], url_path="moderate")
    def moderate(self, request, pk=None) -> Response:
        """Perform action (block, approve, delete) on a reported news article."""
        news = get_object_or_404(News, id=pk)
        
        # Permission check: Platform admin/mod, or community admin/mod (if community-scoped)
        user_profile = getattr(request.user, "profile", None)
        user_role = user_profile.role if user_profile else "student"
        
        is_platform_moderator = user_role in ["admin", "moderator"]
        is_community_moderator = False
        
        if news.scope == News.Scope.COMMUNITY and news.community:
            is_community_moderator = news.community.memberships.filter(
                user=request.user,
                role__in=[
                    CommunityMember.Role.OWNER,
                    CommunityMember.Role.ADMIN,
                    CommunityMember.Role.MODERATOR,
                ]
            ).exists()
            
        if not is_platform_moderator and not is_community_moderator:
            return error_response(message="You do not have permission to moderate this news article.", status_code=status.HTTP_403_FORBIDDEN)
            
        mod_action = request.data.get("action", "").lower().strip()
        if mod_action == "block":
            news.is_blocked = True
            news.save(update_fields=["is_blocked"])
            return success_response(message="News article blocked successfully.")
            
        elif mod_action == "approve":
            news.is_blocked = False
            news.save(update_fields=["is_blocked"])
            # Dismiss reports
            news.reports.all().delete()
            return success_response(message="News article approved and reports cleared.")
            
        elif mod_action == "delete":
            news.delete()
            return success_response(message="News article deleted successfully.")
            
        else:
            return error_response(
                message="Invalid action. Allowed: block, approve, delete.",
                status_code=status.HTTP_400_BAD_REQUEST
            )


class NewsCommentViewSet(viewsets.GenericViewSet):
    queryset = NewsComment.objects.all()
    serializer_class = NewsCommentSerializer
    permission_classes = [permissions.IsAuthenticated, IsCommentAuthorOrModeratorOrReadOnly]

    def destroy(self, request, pk=None) -> Response:
        """Delete a comment."""
        comment = get_object_or_404(NewsComment, id=pk)
        self.check_object_permissions(request, comment)
        comment.delete()
        return success_response(message="Comment deleted.")


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [permissions.IsAuthenticated]

# api/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    FitoutTypeViewSet, RegisterDBByClientAPIView,  FitOutRequestViewSet,
    FitoutDeviationViewSet,
    FitoutChecklistViewSet,
    FitoutRequestChatViewSet,
    FitoutDeviationChatViewSet,
    ChecklistAnswerViewSet,
    SubCategoryViewSet,
    WorkCategoryViewSet,
    StatusViewSet,
    DeviationStatusViewSet,
    # AssociationViewSet,
    ChecklistQuestionViewSet,
    QuestionOptionViewSet,
    FitoutDeviationImageViewSet,
    FitoutGuideViewSet,
    PaymentModeViewSet,
    AnnexureViewSet
)

router = DefaultRouter()


router.register(r'fitout-requests', FitOutRequestViewSet, basename='fitout-request')
router.register(r'fitout-types', FitoutTypeViewSet, basename='fitout-type')
router.register(r'fitout-deviations', FitoutDeviationViewSet, basename='deviation')
router.register(r'fitout-checklists', FitoutChecklistViewSet, basename='checklist')
router.register(r'request-chats', FitoutRequestChatViewSet, basename='request-chat')
router.register(r'deviation-chats', FitoutDeviationChatViewSet, basename='deviation-chat')
router.register(r'checklist-answers', ChecklistAnswerViewSet, basename='checklist-answer')
router.register(r'annexures', AnnexureViewSet, basename='annexure')
router.register(r'work-categories', WorkCategoryViewSet, basename='work-category')
router.register(r'sub-categories', SubCategoryViewSet, basename='sub-category')
router.register(r'statuses', StatusViewSet, basename='status')
router.register(r'deviation-statuses', DeviationStatusViewSet, basename='deviation-status')
# router.register(r'associations', AssociationViewSet, basename='association')
router.register(r'checklist-questions', ChecklistQuestionViewSet, basename='checklist-question')
router.register(r'question-options', QuestionOptionViewSet, basename='question-option')
router.register(r'fitout-deviation-images', FitoutDeviationImageViewSet, basename="fitout-deviation-image")
# router.register(r'fitout-categories', WorkCategoryViewSet, basename='fitout-category')
router.register(r'fitout-guide', FitoutGuideViewSet, basename='fitout-guide')
router.register(r'payment-modes', PaymentModeViewSet, basename='payment-mode')





urlpatterns = [
    path("register-db/", RegisterDBByClientAPIView.as_view(), name="register-db"),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    
    path("auth/login/", obtain_auth_token, name="api_token_auth"),
    path("", include(router.urls)),
]

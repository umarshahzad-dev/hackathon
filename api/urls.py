from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

# Import views from your apps
from users.views import (
    register_user, 
    google_login, 
    get_interests, 
    update_profile,      # <--- THIS WAS MISSING
    get_current_user     # <--- THIS WAS MISSING
)
from core.views import (
    generate_career_plan, 
    generate_internships, 
    grade_internship, 
    create_todo_push, 
    get_todos, 
    complete_todo, 
    get_my_internships, 
    scrape_jobs, 
    travel_planner, 
    local_discounts_and_events,
    enroll_internship,
    sync_internship_resources,
    generate_quiz,
    submit_quiz,
    get_cv,
    update_cv,
    toggle_urgent_todo,
    delete_todo
)
from marketplace.views import (
    create_product, 
    send_offer, 
    product_chat, 
    list_products, 
    manage_offer, 
    get_my_offers, 
    get_my_chats
)

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # --- AUTHENTICATION ---
    path('api/auth/register/', register_user),
    path('api/auth/google/', google_login),
    path('api/auth/interests/', get_interests),
    path('api/token/', TokenObtainPairView.as_view()),
    path('api/token/refresh/', TokenRefreshView.as_view()),

    # --- USER PROFILE ---
    path('api/user/update/', update_profile),       # <--- FIXES YOUR 404 ERROR
    path('api/user/me/', get_current_user),         # <--- Fixes Login Redirect check

    # --- CORE AI FEATURES ---
    path('api/career-plan/', generate_career_plan),
    
    # --- INTERNSHIPS ---
    path('api/internships/generate/', generate_internships),
    path('api/internships/my/', get_my_internships),
    path('api/internships/enroll/<int:internship_id>/', enroll_internship),
    path('api/internships/grade/<int:internship_id>/', grade_internship),
    path('api/internships/sync-resources/<int:internship_id>/', sync_internship_resources),
    path('api/internships/quiz/<int:internship_id>/', generate_quiz),
    path('api/internships/quiz/submit/<int:internship_id>/', submit_quiz),
    
    # --- TODO LIST ---
    path('api/todo/create/', create_todo_push),
    path('api/todo/list/', get_todos),
    path('api/todo/complete/<int:todo_id>/', complete_todo),
    path('api/todo/toggle-urgent/<int:todo_id>/', toggle_urgent_todo),
    path('api/todo/delete/<int:todo_id>/', delete_todo),
    
    # --- EXTERNAL TOOLS ---
    path('api/jobs/scrape/', scrape_jobs),
    path('api/travel/plan/', travel_planner),
    path('api/discounts/', local_discounts_and_events),
    path('api/cv/', get_cv),
    path('api/cv/update/', update_cv),

    # --- MARKETPLACE ---
    path('api/market/list/', list_products),
    path('api/market/create/', create_product),
    path('api/market/offer/send/<int:product_id>/', send_offer),
    path('api/market/offer/my/', get_my_offers),
    path('api/market/offer/manage/<int:offer_id>/', manage_offer),
    path('api/market/chat/<int:product_id>/', product_chat),
    path('api/market/inbox/', get_my_chats),
]
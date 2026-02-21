import os
import json
import re
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from django.core.cache import cache

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

import google.genai as genai
from google.genai import types as genai_types
from firebase_admin import messaging

from .models import CareerPlan, Internship, Enrollment, Todo, CVProfile
from api.serializers import CVProfileSerializer


# ==========================================
# 8. AUTO CV BUILDER
# ==========================================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_cv(request):
    cv, created = CVProfile.objects.get_or_create(user=request.user)
    serializer = CVProfileSerializer(cv)
    return Response(serializer.data)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_cv(request):
    cv, created = CVProfile.objects.get_or_create(user=request.user)
    serializer = CVProfileSerializer(cv, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)


# Load environment variables
load_dotenv()

# ==========================================
# 0. SETUP & CONFIGURATION
# ==========================================
api_key = os.environ.get("GEMINI_API_KEY")

gemini_client = None  # Will be set below if API key is present
GEMINI_MODEL = "gemini-2.0-flash"  # Primary model

if api_key:
    try:
        gemini_client = genai.Client(api_key=api_key)
        print(f"✅ Gemini AI client ready ({GEMINI_MODEL})")
    except Exception as e:
        print(f"❌ Failed to create Gemini client: {e}")
else:
    print("❌ CRITICAL: GEMINI_API_KEY missing in .env")


def ai_generate(prompt):
    """Helper to call Gemini with the new google.genai SDK."""
    if gemini_client is None:
        raise RuntimeError("Gemini client not initialized. Check GEMINI_API_KEY.")
    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    return response.text



def get_lang_instruction(request):
    """Returns an AI prompt suffix based on the Accept-Language header."""
    lang = request.headers.get("Accept-Language", "en")
    if lang == "tr":
        return "\n\nIMPORTANT: Respond ENTIRELY in Turkish (Türkçe). All text, descriptions, titles, and feedback must be in Turkish."
    return ""


# ==========================================
# 1. HELPER: REAL YOUTUBE FETCHING
# ==========================================
def fetch_youtube_resources(search_term):
    """
    Fetches real YouTube videos.
    FALLBACK: If API times out/fails, generates a direct search link.
    """
    yt_api_key = os.environ.get("YOUTUBE_API_KEY")

    # 1. Prepare a backup link (always works)
    fallback_link = [
        {
            "title": f"Watch Tutorial: {search_term}",
            "url": f"https://www.youtube.com/results?search_query={search_term}",
        }
    ]

    if not yt_api_key:
        return fallback_link

    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&maxResults=3&q={search_term}&type=video&key={yt_api_key}"

    try:
        # 2. Add a short TIMEOUT (3 seconds) so it doesn't hang the server
        response = requests.get(url, timeout=3)

        if response.status_code == 200:
            data = response.json()
            links = []
            if "items" in data:
                for item in data["items"]:
                    if "videoId" in item.get("id", {}):
                        video_id = item["id"]["videoId"]
                        title = item["snippet"]["title"]
                        links.append(
                            {
                                "title": title,
                                "url": (
                                    f"https://www.watch-youtube.com/watch?v={video_id}"
                                    if "watch-youtube" in url
                                    else f"https://www.youtube.com/watch?v={video_id}"
                                ),
                            }
                        )
            return links if links else fallback_link
        else:
            print(f"⚠️ YouTube API Non-200 Response: {response.status_code}")
            return fallback_link

    except Exception as e:
        print(f"⚠️ YouTube Fetch Error (Using Fallback): {e}")
        # Return the manual link so the UI doesn't look empty
        return fallback_link


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_internship_resources(request, internship_id):
    """
    Manually triggers a resource refresh for an internship.
    Used if initial generation failed to fetch videos.
    """
    try:
        internship = Internship.objects.get(id=internship_id)
        # Use title as search term if we don't store the original search term
        yt_links = fetch_youtube_resources(f"{internship.title} tutorial")
        internship.youtube_links = yt_links
        internship.save()
        return Response({"status": "Resources Synced", "youtube_links": yt_links})
    except Internship.DoesNotExist:
        return Response({"error": "Internship not found"}, status=404)


# ==========================================
# 2. AI CAREER PLANNER
# ==========================================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_career_plan(request):
    user = request.user
    extra_info = request.data.get("extra_info", "").strip()

    # If no specific extra_info is provided, try to fetch the most recent plan first
    if not extra_info:
        existing_plan = (
            CareerPlan.objects.filter(user=user).order_by("-created_at").first()
        )
        if existing_plan:
            try:
                import json

                plan_json = json.loads(existing_plan.plan_details)
                print("♻️  Fetching cached AI career plan.")
                return Response(
                    {
                        "status": "success",
                        "career_plan": plan_json,
                        "plan_id": existing_plan.id,
                        "cached": True,
                    }
                )
            except Exception as e:
                pass  # Silently fail and generate a new one if old one wasn't valid JSON

    # If we get here, generate a new plan
    extra_prompt = extra_info if extra_info else "I want to explore the best options."

    prompt = f"""
    Create a step-by-step career plan for a user with the following profile:
    Occupation: {user.occupation}
    Interests: {user.interests}
    Experience Level: {user.experience_level} out of 5 stars.
    Extra details: {extra_prompt}
    
    You MUST output ONLY a raw JSON array of objects representing steps in a roadmap.
    Each object must have these exactly keys:
    "step_number": integer
    "title": "Short string title for the node",
    "description": "1 short sentence maximum (keep it extremely brief, under 15 words).",
    "timeframe": "Short time (e.g., '1 wk', '2 mos')",
    "type": "milestone" | "learning" | "project" | "job"
    
    Make it 4 to 6 steps long. DO NOT include markdown wrappers or backticks. Just the pure JSON array.
    """

    try:
        text_response = ai_generate(prompt).strip()

        # Clean response text in case AI adds markdown
        if "```json" in text_response:
            text_response = text_response.split("```json")[1].split("```")[0].strip()
        elif "```" in text_response:
            text_response = text_response.split("```")[1].split("```")[0].strip()

        # Save to DB (optional: save the raw json string)
        plan = CareerPlan.objects.create(user=user, plan_details=text_response)

        # We try to load it and return as distinct nodes
        import json

        plan_json = json.loads(text_response)

        return Response(
            {"status": "success", "career_plan": plan_json, "plan_id": plan.id}
        )
    except Exception as e:
        return Response({"error": str(e)}, status=500)


# ==========================================
# 3. AI INTERNSHIPS
# ==========================================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_internships(request):
    user = request.user
    occupation = user.occupation if user.occupation else "Software Developer"

    print(f"🤖 Generating internships for: {occupation}")

    if gemini_client is None:
        return Response(
            {"error": "AI model not initialized. Check GEMINI_API_KEY."}, status=500
        )

    # 🛡️ PROTECT enrolled / graded internships — only delete untouched ones
    enrolled_ids = set(
        Enrollment.objects.filter(user=user).values_list("internship_id", flat=True)
    )
    unenrolled = Internship.objects.filter(user=user).exclude(id__in=enrolled_ids)
    deleted_count = unenrolled.count()
    unenrolled.delete()
    print(
        f"🗑️ Cleaned {deleted_count} unenrolled internships (kept {len(enrolled_ids)} enrolled/graded)"
    )

    # Generate fresh ones with AI
    prompt = f"""
    Create exactly 5 realistic, step-by-step mock internships for a user learning '{occupation}'.
    Return ONLY a raw JSON array format with these exact keys:
    "title", "min_days" (integer between 7-30), "max_days" (integer between 7-30), "description", "skills_learned", "ai_text" (a motivational intro), "youtube_search_term" (string to search on YT), "questions" (array of 3 interview question strings).
    Do NOT include Markdown wrappers like ```json, just the pure array [ ... ].
    """
    try:
        text_response = ai_generate(prompt)
        match = re.search(r"\[.*\]", text_response, re.DOTALL)
        if match:
            internships_data = json.loads(match.group())
        else:
            cleaned = text_response.replace("```json", "").replace("```", "").strip()
            internships_data = json.loads(cleaned)
    except Exception as e:
        print(f"❌ GENERATION ERROR: {str(e)}")
        return Response({"error": f"AI generation failed: {str(e)}"}, status=500)

    try:
        saved_internships = []
        for item in internships_data:
            if isinstance(item, str):
                continue

            search_term = item.get(
                "youtube_search_term", f"{item.get('title', 'coding')} tutorial"
            )
            yt_links = fetch_youtube_resources(search_term)

            intern = Internship.objects.create(
                user=user,
                title=item.get("title", "Exciting Internship"),
                min_days=item.get("min_days", 7),
                max_days=item.get("max_days", 30),
                description=item.get("description", ""),
                skills_learned=item.get("skills_learned", ""),
                ai_generated_text=item.get("ai_text", ""),
                youtube_links=yt_links,
                interview_questions=item.get("questions", []),
                image_url="https://res.cloudinary.com/demo/image/upload/v1312461204/sample.jpg",
            )
            saved_internships.append({"id": intern.id, "title": intern.title})

        return Response(
            {
                "status": f"Generated {len(saved_internships)} new internships! Your enrolled ones are safe.",
                "data": saved_internships,
            }
        )

    except Exception as e:
        print(f"❌ SAVE ERROR: {str(e)}")
        return Response({"error": f"Server Error: {str(e)}"}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_my_internships(request):
    internships = Internship.objects.filter(user=request.user).order_by("-created_at")
    data = []
    for intern in internships:
        enrollment = Enrollment.objects.filter(
            user=request.user, internship=intern
        ).first()
        data.append(
            {
                "id": intern.id,
                "title": intern.title,
                "description": intern.description,
                "min_days": intern.min_days,
                "max_days": intern.max_days,
                "image_url": intern.image_url,
                "skills_learned": intern.skills_learned,
                "youtube_links": intern.youtube_links,
                "ai_generated_text": intern.ai_generated_text,
                "status": enrollment.status if enrollment else "New",
                "score": enrollment.ai_score if enrollment else None,
                "feedback": enrollment.ai_feedback if enrollment else None,
            }
        )
    return Response(data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def enroll_internship(request, internship_id):
    try:
        internship = Internship.objects.get(id=internship_id)
        obj, created = Enrollment.objects.get_or_create(
            user=request.user, internship=internship, defaults={"status": "Enrolled"}
        )
        return Response({"status": "Enrolled successfully!", "enrollment_id": obj.id})
    except Internship.DoesNotExist:
        return Response({"error": "Internship not found"}, status=404)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def grade_internship(request, internship_id):
    user = request.user
    try:
        internship = Internship.objects.get(id=internship_id)
    except Internship.DoesNotExist:
        return Response({"error": "Internship not found"}, status=404)

    repo_link = request.data.get("repo_link")
    time_taken = request.data.get("time_taken")
    difficulty = request.data.get("difficulty")
    user_rating = request.data.get("user_rating")

    prompt = f"""
    The user submitted a GitHub repository: {repo_link} for project '{internship.title}'.
    Provide a score out of 100 and brief feedback.
    Format STRICTLY:
    SCORE: 85
    FEEDBACK: Good work.
    """

    try:
        ai_resp = ai_generate(prompt)
        score = 80
        match = re.search(r"SCORE:\s*(\d+)", ai_resp)
        if match:
            score = int(match.group(1))

        enrollment, created = Enrollment.objects.get_or_create(
            user=user, internship=internship
        )
        enrollment.status = "Graded"
        enrollment.repo_link = repo_link
        enrollment.time_taken_days = time_taken
        enrollment.difficulty_rating = difficulty
        enrollment.user_rating = user_rating
        enrollment.ai_score = score
        enrollment.ai_feedback = ai_resp
        enrollment.save()

        return Response({"message": "Graded!", "score": score, "feedback": ai_resp})

    except Exception as e:
        return Response({"error": f"Grading failed: {str(e)}"}, status=500)


# ==========================================
# 4B. QUIZ EXAM SYSTEM
# ==========================================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_quiz(request, internship_id):
    """Generate 10 MCQ questions for an internship exam."""
    try:
        internship = Internship.objects.get(id=internship_id)
    except Internship.DoesNotExist:
        return Response({"error": "Internship not found"}, status=404)

    # 1. Check if the quiz was already generated and saved in DB for this internship
    if (
        internship.interview_questions
        and len(internship.interview_questions) >= 10
        and isinstance(internship.interview_questions[0], dict)
        and "options" in internship.interview_questions[0]
    ):
        print("♻️ Fetching pre-built quiz from DB.")
        questions = internship.interview_questions
    else:
        # 2. Check if a quiz for this exact title was generated globally by another user
        safe_title = re.sub(r"[^a-zA-Z0-9]", "_", internship.title.lower())
        cache_key = f"quiz_shared_{safe_title}"
        questions = cache.get(cache_key)

        if not questions:
            # 3. Generate with AI
            prompt = f"""
            Create exactly 10 multiple choice questions for a certification exam on "{internship.title}".
            Skills covered: {internship.skills_learned}
            
            Return ONLY a raw JSON array. Each question object must have:
            - "question": the question text
            - "options": array of exactly 4 string choices (A, B, C, D)
            - "correct": index of the correct answer (0-3)
            
            Make questions progressively harder. Mix theory and practical scenarios.
            Do NOT include markdown wrappers. Just the pure array [ ... ].
            """

            try:
                text_response = ai_generate(prompt)
                match = re.search(r"\[.*\]", text_response, re.DOTALL)
                if match:
                    questions = json.loads(match.group())
                else:
                    cleaned = (
                        text_response.replace("```json", "").replace("```", "").strip()
                    )
                    questions = json.loads(cleaned)

                cache.set(
                    cache_key, questions, timeout=86400
                )  # Cache for 24 hours globally
            except Exception as e:
                print(f"Quiz generation error: {e}")
                return Response(
                    {"error": f"Failed to generate quiz: {str(e)}"}, status=500
                )

        # Store questions on the internship for later grading
        internship.interview_questions = questions
        internship.save()

    # Return questions WITHOUT the correct answers
    safe_questions = []
    for q in questions:
        safe_questions.append(
            {
                "question": q.get("question", ""),
                "options": q.get("options", []),
            }
        )

    return Response({"questions": safe_questions, "total": len(safe_questions)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_quiz(request, internship_id):
    """Grade submitted quiz answers. Need 60% to pass."""
    try:
        internship = Internship.objects.get(id=internship_id)
    except Internship.DoesNotExist:
        return Response({"error": "Internship not found"}, status=404)

    answers = request.data.get("answers", [])  # List of selected indices
    questions = internship.interview_questions or []

    if not questions:
        return Response({"error": "No quiz found. Generate one first."}, status=400)

    correct_count = 0
    total = len(questions)
    results = []

    for i, q in enumerate(questions):
        user_answer = answers[i] if i < len(answers) else -1
        correct_idx = q.get("correct", 0)
        is_correct = user_answer == correct_idx
        if is_correct:
            correct_count += 1
        results.append(
            {
                "question": q.get("question", ""),
                "your_answer": user_answer,
                "correct_answer": correct_idx,
                "is_correct": is_correct,
            }
        )

    score = round((correct_count / total) * 100) if total > 0 else 0
    passed = score >= 60

    # Update enrollment record
    enrollment, _ = Enrollment.objects.get_or_create(
        user=request.user, internship=internship
    )
    enrollment.ai_score = score
    enrollment.ai_feedback = f"Quiz Result: {correct_count}/{total} correct ({score}%). {'PASSED ✅' if passed else 'FAILED ❌'}"
    if passed:
        enrollment.status = "Graded"
    enrollment.save()

    return Response(
        {
            "score": score,
            "correct": correct_count,
            "total": total,
            "passed": passed,
            "results": results,
            "feedback": enrollment.ai_feedback,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_todo_push(request):
    title = request.data.get("title")
    is_urgent = request.data.get("is_urgent", False)
    user = request.user
    Todo.objects.create(user=user, title=title, is_urgent=is_urgent)
    return Response({"status": "Todo Created!"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_todos(request):
    todos = Todo.objects.filter(user=request.user).order_by("-is_urgent", "-id")
    return Response({"todos": list(todos.values())})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_urgent_todo(request, todo_id):
    try:
        todo = Todo.objects.get(id=todo_id, user=request.user)
        todo.is_urgent = not todo.is_urgent
        todo.save()
        return Response({"status": "Urgency Toggled!", "is_urgent": todo.is_urgent})
    except Todo.DoesNotExist:
        return Response({"error": "Not found"}, status=404)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def complete_todo(request, todo_id):
    try:
        todo = Todo.objects.get(id=todo_id, user=request.user)
        todo.is_completed = True
        todo.save()
        return Response({"status": "Completed!"})
    except Todo.DoesNotExist:
        return Response({"error": "Not found"}, status=404)


@api_view(["DELETE", "POST"])
@permission_classes([IsAuthenticated])
def delete_todo(request, todo_id):
    try:
        todo = Todo.objects.get(id=todo_id, user=request.user)
        todo.delete()
        return Response({"status": "Deleted!"})
    except Todo.DoesNotExist:
        return Response({"error": "Not found"}, status=404)


# ==========================================
# 6. SCRAPING
# ==========================================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def scrape_jobs(request):
    import requests
    from .models import ScrapedJob

    user = request.user

    # 1. Get search params from frontend (or fall back to profile)
    query = request.query_params.get("query", "").strip()
    location_filter = request.query_params.get("location", "").strip()

    # If no query provided, use profile data
    if not query:
        if user.occupation:
            query = user.occupation
        elif user.skills and len(user.skills) > 0:
            query = user.skills[0]
        else:
            query = "Software Developer"

    # If no location, try user's profile location
    if not location_filter:
        if user.city:
            location_filter = user.city
        elif user.country:
            location_filter = user.country

    print(f"🔍 Job Search: query='{query}', location='{location_filter}'")

    cache_key = f"jobs_v2_{query.replace(' ', '_').lower()}_{location_filter.replace(' ', '_').lower()}"
    jobs_data = cache.get(cache_key)

    if not jobs_data:
        print(f"🤖 Generating AI dummy jobs for: {query} in {location_filter}")
        prompt = f"""
        Generate exactly 15 highly realistic job postings for the role of '{query}' located in or near '{location_filter}' (or remote).
        Make them look like authentic, real-world listings from top known companies and startups.
        Return ONLY a raw JSON array of objects with these exact keys:
        "title" (string), 
        "company" (string), 
        "location" (string), 
        "link" (string, just make it realistic like 'https://linkedin.com/jobs/view/12345'), 
        "source" (string, randomly pick from: 'LinkedIn', 'Glassdoor', 'Indeed', 'Wellfound', 'ZipRecruiter'), 
        "description" (string, a short 1-2 sentence snippet of the job role).
        Do NOT include Markdown wrappers like ```json. Just the pure array [ ... ].
        """
        try:
            text_response = ai_generate(prompt).strip()

            # Clean response text in case AI adds markdown
            if "```json" in text_response:
                text_response = (
                    text_response.split("```json")[1].split("```")[0].strip()
                )
            elif "```" in text_response:
                text_response = text_response.split("```")[1].split("```")[0].strip()

            # Defensive parsing
            match = re.search(r"\[.*\]", text_response, re.DOTALL)
            if match:
                jobs_data = json.loads(match.group())
            else:
                jobs_data = json.loads(text_response)

            cache.set(cache_key, jobs_data, timeout=86400)  # Cache for 24 hours
            print(f"✨ Custom AI Jobs Cached!")
        except Exception as e:
            print(f"❌ Job Generation Error: {e}")
            jobs_data = []  # Fallback
    else:
        print(f"♻️ Fetched jobs for {query} from cache!")

    # Clear old jobs for this user to keep it fresh
    ScrapedJob.objects.filter(user=user).delete()
    all_jobs = []

    # Save the new jobs to the database for this specific user
    if jobs_data:
        for job in jobs_data:
            try:
                import urllib.parse

                search_term = f"{job.get('title', query)} job {job.get('company', '')}"
                safe_link = f"https://www.google.com/search?q={urllib.parse.quote_plus(search_term)}"

                new_job = ScrapedJob.objects.create(
                    user=user,
                    title=job.get("title", f"{query} Professional"),
                    company=job.get("company", "Tech Innovations Inc."),
                    location=job.get("location", location_filter or "Remote"),
                    link=safe_link,
                    source=job.get("source", "Web"),
                    description=job.get("description", "A fantastic opportunity."),
                )
                all_jobs.append(
                    {
                        "id": new_job.id,
                        "title": new_job.title,
                        "company": new_job.company,
                        "location": new_job.location,
                        "link": new_job.link,
                        "source": new_job.source,
                        "description": new_job.description,
                    }
                )
            except Exception as e:
                pass

    return Response(
        {
            "status": "success",
            "count": len(all_jobs),
            "query_used": query,
            "location_used": location_filter,
            "jobs": all_jobs,
        }
    )


# ==========================================
# 7. TRAVEL & LOCAL (THE MISSING FUNCTION!)
# ==========================================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def travel_planner(request):
    """This was missing! It generates the travel plan and link"""
    from_loc = request.data.get("from", "City")
    to_loc = request.data.get("to", "Destination")
    date = request.data.get("date", "anytime")

    prompt = f"""
    Act as a travel guide. Suggest 5 incredibly popular places to visit in {to_loc}. 
    Return a pure JSON array with objects: "name", "description".
    """

    try:
        ai_response = ai_generate(prompt)
        match = re.search(r"\[.*\]", ai_response, re.DOTALL)
        plan_json = match.group() if match else "[]"
    except:
        plan_json = "[]"

    # Smart Link Generation
    skyscanner_link = (
        f"https://www.skyscanner.com/transport/flights/{from_loc}/{to_loc}/{date}"
    )

    return Response(
        {
            "status": "success",
            "travel_plan": plan_json,
            "flight_search_url": skyscanner_link,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def local_discounts_and_events(request):
    """Returns local events, deals, and vibes using AI. Caches permanently in DB by city+country."""
    from .models import LocalVibe

    user = request.user
    city = (user.city or "New York").strip()
    country = (user.country or "USA").strip()
    refresh = request.query_params.get("refresh", "false").lower() == "true"

    # -- DB LOOKUP FIRST --
    if not refresh:
        existing = LocalVibe.objects.filter(
            city__iexact=city, country__iexact=country
        ).first()
        if existing and existing.offers:
            print(f"\u267b\ufe0f Fetched '{city}, {country}' vibes from DB!")
            return Response(
                {"location": f"{city}, {country}", "active_offers": existing.offers}
            )

    # -- REFRESH: wipe stale DB record --
    if refresh:
        print(f"\U0001f504 Refresh: deleting old DB vibes for {city}...")
        LocalVibe.objects.filter(city__iexact=city, country__iexact=country).delete()

    print(f"\u2728 Generating fresh vibes for {city}, {country} via AI...")
    prompt = f"""
    Find or generate 6-8 incredible 'local vibes' for someone living in {city}, {country}.
    These should be a mix of:
    - Current shopping discounts or sales.
    - Upcoming community events or festivals.
    - Trending local food spots or happy hour deals.
    - Career-related meetups or student discounts.

    Return ONLY a raw JSON array of objects with these keys:
    "title", "type" (one of: 'Deal', 'Event', 'Food', 'Career'), "description", "value" (e.g. '50% Off' or 'Free Entry'), "location_detail", "image_query" (a specific short string to use for an image search).

    Do NOT include any markdown or extra text. Output pure JSON.
    """

    try:
        response = ai_generate(prompt)
        cleaned = response.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        events = json.loads(match.group() if match else cleaned)

        # Save to DB so next request is instant
        LocalVibe.objects.update_or_create(
            city=city, country=country, defaults={"offers": events}
        )
        print(f"\U0001f4be Saved {len(events)} vibes to DB for {city}!")

    except Exception as e:
        print(f"\u274c Vibe Generation Error: {e}")
        # Return stale DB data if any, rather than dummy
        fallback = LocalVibe.objects.filter(
            city__iexact=city, country__iexact=country
        ).first()
        if fallback and fallback.offers:
            return Response(
                {"location": f"{city}, {country}", "active_offers": fallback.offers}
            )
        events = [
            {
                "title": "Global Fusion Festival",
                "type": "Event",
                "description": "A celebration of local culture and food.",
                "value": "Free Entry",
                "location_detail": "Downtown Plaza",
                "image_query": "festival crowd",
            },
            {
                "title": "Tech Career Mixer",
                "type": "Career",
                "description": "Networking with local innovators.",
                "value": "Invite Only",
                "location_detail": "Innovation Hub",
                "image_query": "networking event",
            },
            {
                "title": "Student Night Out",
                "type": "Deal",
                "description": "Exclusive discounts for verified students.",
                "value": "30% Off Everything",
                "location_detail": "City Center",
                "image_query": "shopping mall",
            },
        ]

    return Response({"location": f"{city}, {country}", "active_offers": events})

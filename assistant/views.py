from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import (
    Memory,
    Conversation,
    Reminder,
    PersonalMemory,
    UserProfile,
    MoodLog,
    UserGoal,
    GoalStep,
    HabitTracker,
    HabitLog,
    Task,
    Subject,
    Assignment,
    Exam,
    MediaPreference,
)
from django.db import models
from django.utils import timezone
from django.db.models import OuterRef, Subquery, Q
import requests
import os
import json
import re
import datetime
from urllib.parse import quote_plus
import time


def chat_page(request):
    conversations = Conversation.objects.all().order_by('-created_at')
    return render(request, 'chat.html', {"conversations": conversations})


def history_page(request):
    """Display full conversation history with search/filtering."""
    conversations = Conversation.objects.all().order_by('-created_at')
    return render(request, 'history.html', {"conversations": conversations})


def history_api(request):
    """API endpoint to retrieve conversation history with optional search."""
    search_query = request.GET.get('search', '').strip()
    conv_id = request.GET.get('conv_id')
    
    if conv_id:
        # Get specific conversation with full message history
        try:
            conversation = Conversation.objects.get(id=conv_id)
            memories = Memory.objects.filter(conversation=conversation).order_by('created_at')
            return JsonResponse({
                'conversation': {
                    'id': conversation.id,
                    'title': conversation.title,
                    'created_at': conversation.created_at.isoformat(),
                    'is_pinned': conversation.is_pinned,
                    'messages': [
                        {
                            'message': m.message,
                            'response': m.response,
                            'created_at': m.created_at.isoformat(),
                        }
                        for m in memories
                    ]
                }
            })
        except Conversation.DoesNotExist:
            return JsonResponse({'error': 'Conversation not found'}, status=404)
    
    # Get all conversations (with optional search)
    conversations = Conversation.objects.all()
    
    if search_query:
        # Search by title or message content
        conversations = conversations.filter(
            models.Q(title__icontains=search_query) |
            models.Q(memory__message__icontains=search_query) |
            models.Q(memory__response__icontains=search_query)
        ).distinct()
    
    conversations = conversations.order_by('-created_at')
    
    # Build response with preview
    result = []
    for conv in conversations[:50]:  # Limit to 50 most recent
        last_message = Memory.objects.filter(conversation=conv).order_by('-created_at').first()
        result.append({
            'id': conv.id,
            'title': conv.title,
            'created_at': conv.created_at.isoformat(),
            'is_pinned': conv.is_pinned,
            'message_count': Memory.objects.filter(conversation=conv).count(),
            'preview': last_message.message[:100] if last_message else '',
        })
    
    return JsonResponse({'conversations': result})


def habit_tracker_page(request):
    """Display habit tracker page."""
    habits = HabitTracker.objects.filter(is_active=True).order_by('-created_at')
    return render(request, 'habit_tracker.html', {'habits': habits})


@csrf_exempt
def habit_tracker_api(request):
    """API endpoint for habit tracker operations."""
    if request.method == 'POST':
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        action = payload.get('action')
        
        # Create new habit
        if action == 'create':
            name = payload.get('name', '').strip()
            if not name:
                return JsonResponse({'error': 'Habit name is required'}, status=400)
            
            description = payload.get('description', '').strip()
            frequency = payload.get('frequency', 'daily')
            target_days = payload.get('target_days', '1,2,3,4,5,6,0')
            
            habit = HabitTracker.objects.create(
                name=name,
                description=description,
                frequency=frequency,
                target_days=target_days
            )
            
            return JsonResponse({
                'success': True,
                'habit': {
                    'id': habit.id,
                    'name': habit.name,
                    'frequency': habit.frequency,
                }
            })
        
        # Update habit
        if action == 'update':
            habit_id = payload.get('habit_id')
            if not habit_id:
                return JsonResponse({'error': 'habit_id is required'}, status=400)
            
            try:
                habit = HabitTracker.objects.get(id=habit_id)
            except HabitTracker.DoesNotExist:
                return JsonResponse({'error': 'Habit not found'}, status=404)
            
            if 'name' in payload:
                habit.name = payload['name']
            if 'description' in payload:
                habit.description = payload['description']
            if 'frequency' in payload:
                habit.frequency = payload['frequency']
            if 'target_days' in payload:
                habit.target_days = payload['target_days']
            if 'is_active' in payload:
                habit.is_active = payload['is_active']
            
            habit.save()
            
            return JsonResponse({'success': True})
        
        # Delete habit
        if action == 'delete':
            habit_id = payload.get('habit_id')
            if not habit_id:
                return JsonResponse({'error': 'habit_id is required'}, status=400)
            
            try:
                habit = HabitTracker.objects.get(id=habit_id)
                habit.delete()
                return JsonResponse({'success': True})
            except HabitTracker.DoesNotExist:
                return JsonResponse({'error': 'Habit not found'}, status=404)
        
        # Log habit completion
        if action == 'log':
            habit_id = payload.get('habit_id')
            if not habit_id:
                return JsonResponse({'error': 'habit_id is required'}, status=400)
            
            date_str = payload.get('date', timezone.now().date().isoformat())
            completed = payload.get('completed', True)
            notes = payload.get('notes', '')
            mood_before = payload.get('mood_before', '')
            mood_after = payload.get('mood_after', '')
            
            try:
                habit = HabitTracker.objects.get(id=habit_id)
            except HabitTracker.DoesNotExist:
                return JsonResponse({'error': 'Habit not found'}, status=404)
            
            # Get or create log for this date
            log, created = HabitLog.objects.get_or_create(
                habit=habit,
                date=date_str,
                defaults={
                    'completed': completed,
                    'notes': notes,
                    'mood_before': mood_before,
                    'mood_after': mood_after,
                }
            )
            
            if not created:
                log.completed = completed
                log.notes = notes
                log.mood_before = mood_before
                log.mood_after = mood_after
                log.save()
            
            return JsonResponse({
                'success': True,
                'log': {
                    'id': log.id,
                    'date': log.date.isoformat(),
                    'completed': log.completed,
                }
            })
        
        return JsonResponse({'error': 'Unknown action'}, status=400)
    
    # GET request - retrieve habits
    habit_id = request.GET.get('habit_id')
    
    if habit_id:
        # Get specific habit with logs
        try:
            habit = HabitTracker.objects.get(id=habit_id)
            logs = habit.logs.order_by('-date')[:90]  # Last 90 days
            
            return JsonResponse({
                'habit': {
                    'id': habit.id,
                    'name': habit.name,
                    'description': habit.description,
                    'frequency': habit.frequency,
                    'target_days': habit.target_days,
                    'is_active': habit.is_active,
                    'current_streak': habit.current_streak,
                    'best_streak': habit.best_streak,
                    'completion_rate': habit.completion_rate,
                    'logs': [
                        {
                            'date': log.date.isoformat(),
                            'completed': log.completed,
                            'notes': log.notes,
                            'mood_before': log.mood_before,
                            'mood_after': log.mood_after,
                        }
                        for log in logs
                    ]
                }
            })
        except HabitTracker.DoesNotExist:
            return JsonResponse({'error': 'Habit not found'}, status=404)
    
    # Get all habits
    habits = HabitTracker.objects.filter(is_active=True).order_by('-created_at')
    
    result = []
    for habit in habits:
        today_log = habit.logs.filter(date=timezone.now().date()).first()
        
        result.append({
            'id': habit.id,
            'name': habit.name,
            'description': habit.description,
            'frequency': habit.frequency,
            'current_streak': habit.current_streak,
            'best_streak': habit.best_streak,
            'completion_rate': habit.completion_rate,
            'completed_today': today_log.completed if today_log else False,
            'created_at': habit.created_at.isoformat(),
        })
    
    return JsonResponse({'habits': result})


def goals_page(request):
    """Display goals dashboard."""
    active_goal = _get_active_goal()
    completed_goals = UserGoal.objects.filter(status='completed').order_by('-updated_at')[:10]
    
    goal_data = None
    if active_goal:
        steps = list(active_goal.steps.order_by('step_order').values('id', 'step_order', 'text', 'is_done'))
        total = len(steps)
        done = sum(1 for s in steps if s['is_done'])
        goal_data = {
            'id': active_goal.id,
            'title': active_goal.title,
            'steps': steps,
            'progress': (done / total * 100) if total > 0 else 0,
            'completed': done,
            'total': total,
        }
    
    return render(request, 'goals.html', {
        'active_goal': goal_data,
        'completed_goals': completed_goals,
    })


def task_manager_page(request):
    """Display task manager page."""
    return render(request, 'task_manager.html')


def student_dashboard(request):
    """Display student dashboard."""
    subjects = Subject.objects.all().order_by('name')
    upcoming_exams = Exam.objects.filter(exam_date__gte=timezone.now()).order_by('exam_date')[:5]
    pending_assignments = Assignment.objects.filter(is_completed=False).order_by('due_date')[:5]
    
    return render(request, 'student_dashboard.html', {
        'subjects': subjects,
        'upcoming_exams': upcoming_exams,
        'pending_assignments': pending_assignments,
    })


def student_api(request):
    """API endpoint for student features."""
    if request.method == 'POST':
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        action = payload.get('action')
        
        # Add Subject
        if action == 'add_subject':
            name = payload.get('name', '').strip()
            if not name:
                return JsonResponse({'error': 'Subject name required'}, status=400)
            sub, created = Subject.objects.get_or_create(name__iexact=name, defaults={'name': name})
            return JsonResponse({'success': True, 'message': f"Subject '{sub.name}' added!"})
            
        # Add Assignment
        elif action == 'add_assignment':
            title = payload.get('title', '').strip()
            subject_name = payload.get('subject', '').strip()
            if not title:
                return JsonResponse({'error': 'Title required'}, status=400)
            
            subject = None
            if subject_name:
                subject = Subject.objects.filter(name__iexact=subject_name).first()
            
            if not subject:
                return JsonResponse({'error': f"Subject '{subject_name}' not found. Please add it first."}, status=404)
                
            due = payload.get('due_date')
            assignment = Assignment.objects.create(
                subject=subject,
                title=title,
                description=payload.get('description', ''),
                due_date=due
            )
            return JsonResponse({'success': True, 'message': f"Assignment '{title}' added for {subject.name}!"})

        # Complete Assignment
        elif action == 'complete_assignment':
            query = payload.get('title', '').strip()
            assignment = Assignment.objects.filter(title__icontains=query, is_completed=False).first()
            if assignment:
                assignment.is_completed = True
                assignment.save()
                return JsonResponse({'success': True, 'message': f"Assignment '{assignment.title}' marked as done!"})
            return JsonResponse({'error': 'Assignment not found'}, status=404)

        # Add Exam
        elif action == 'add_exam':
            title = payload.get('title', '').strip()
            exam_date = payload.get('date')
            subject_name = payload.get('subject', '').strip()
            
            if not title or not exam_date:
                return JsonResponse({'error': 'Title and Date required'}, status=400)
            
            subject = None
            if subject_name:
                subject = Subject.objects.filter(name__iexact=subject_name).first()
                
            exam = Exam.objects.create(
                subject=subject,
                title=title,
                exam_date=exam_date,
                topics=payload.get('topics', '')
            )
            return JsonResponse({'success': True, 'message': f"Exam '{title}' added!"})

    # GET request - get data
    subjects = list(Subject.objects.values('id', 'name', 'color'))
    assignments = list(Assignment.objects.filter(is_completed=False).order_by('due_date').values('id', 'title', 'subject__name', 'due_date'))
    exams = list(Exam.objects.filter(exam_date__gte=timezone.now()).order_by('exam_date').values('id', 'title', 'subject__name', 'exam_date'))

    return JsonResponse({
        'subjects': subjects,
        'assignments': assignments,
        'exams': exams
    })


def task_manager_api(request):
    """API endpoint for task management."""
    if request.method == 'POST':
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        action = payload.get('action')
        
        # Create task
        if action == 'create':
            title = payload.get('title', '').strip()
            if not title:
                return JsonResponse({'error': 'Title is required'}, status=400)
            
            task = Task.objects.create(
                title=title,
                description=payload.get('description', ''),
                priority=payload.get('priority', 'medium'),
                due_date=payload.get('due_date')
            )
            return JsonResponse({
                'success': True,
                'task': {
                    'id': task.id,
                    'title': task.title,
                    'description': task.description,
                    'priority': task.priority,
                    'is_completed': task.is_completed,
                    'due_date': task.due_date.isoformat() if task.due_date else None,
                    'created_at': task.created_at.isoformat(),
                }
            })
        
        # Update task (complete, delete, edit)
        elif action == 'update':
            task_id = payload.get('task_id')
            try:
                task = Task.objects.get(id=task_id)
            except Task.DoesNotExist:
                return JsonResponse({'error': 'Task not found'}, status=404)
            
            if 'is_completed' in payload:
                task.is_completed = payload['is_completed']
            if 'title' in payload:
                task.title = payload['title']
            if 'description' in payload:
                task.description = payload['description']
            if 'priority' in payload:
                task.priority = payload['priority']
            if 'due_date' in payload:
                task.due_date = payload['due_date']
            
            task.save()
            return JsonResponse({'success': True})
            
        # Delete task
        elif action == 'delete':
            task_id = payload.get('task_id')
            try:
                task = Task.objects.get(id=task_id)
                task.delete()
                return JsonResponse({'success': True})
            except Task.DoesNotExist:
                return JsonResponse({'error': 'Task not found'}, status=404)

    # GET request - list tasks
    filter_status = request.GET.get('status', 'all') # all, pending, completed
    tasks = Task.objects.all()
    
    if filter_status == 'pending':
        tasks = tasks.filter(is_completed=False)
    elif filter_status == 'completed':
        tasks = tasks.filter(is_completed=True)
    
    tasks = tasks.order_by('-created_at')
    
    return JsonResponse({
        'tasks': [
            {
                'id': t.id,
                'title': t.title,
                'description': t.description,
                'priority': t.priority,
                'is_completed': t.is_completed,
                'due_date': t.due_date.isoformat() if t.due_date else None,
                'created_at': t.created_at.isoformat(),
            } for t in tasks
        ]
    })


def _system_prompt() -> str:
    return os.getenv(
        "ASSISTANT_SYSTEM_PROMPT",
        "You are a goal-oriented, emotionally intelligent life assistant. "
        "Sound human and warm, not robotic. "
        "Notice emotional cues; respond with empathy before solutions. "
        "Ask brief clarifying questions only when necessary. "
        "Give practical and safe advice. Not a therapist or doctor. "
        "Keep replies concise (1-5 sentences) unless asked for detail. "
        "Prefer conversational language over bullet points.\n\n"
        
        "GOAL-DRIVEN BEHAVIOR:\n"
        "- Understand what users want to achieve\n"
        "- Suggest creating trackable goals when they express desires\n"
        "- Help break big objectives into small steps\n"
        "- Reference active goals naturally in conversations\n"
        "- Celebrate progress and encourage next steps\n"
        "- Ask about goals when relevant\n"
        "- Offer to create action plans when users seem stuck\n"
        "- Balance goal-focus with empathy—never pushy"
    )


def _max_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _truncate(s: str, max_chars: int) -> str:
    s = (s or "").strip()
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 3] + "..."


def _get_user_profile() -> UserProfile:
    profile = UserProfile.objects.first()
    if profile:
        return profile
    return UserProfile.objects.create()


def _get_active_goal() -> UserGoal | None:
    return UserGoal.objects.filter(is_active=True).order_by("-updated_at").first()


def _goal_context_text() -> str:
    goal = _get_active_goal()
    if not goal:
        return (
            "Goal context: no active goal.\n"
            "IMPORTANT: You are a GOAL-ORIENTED AI assistant. "
            "Always try to understand what the user wants to achieve. "
            "If they mention wanting to accomplish something, suggest creating a goal to track progress. "
            "Be proactive in helping them break down big objectives into manageable steps."
        )
    steps = list(goal.steps.order_by("step_order").values("step_order", "text", "is_done")[:8])
    if not steps:
        return (
            f"Goal context:\n"
            f"- Active goal: {goal.title}\n"
            f"- Steps: none yet\n\n"
            f"IMPORTANT: The user is working towards: {goal.title}. "
            f"Help them create a plan by suggesting concrete steps. "
            f"Reference this goal naturally in your responses. "
            f"Encourage progress and celebrate small wins."
        )
    lines = [
        f"Goal context:",
        f"- Active goal: {goal.title}",
        f"- Steps:",
    ]
    completed_steps = [s for s in steps if s["is_done"]]
    pending_steps = [s for s in steps if not s["is_done"]]
    
    for s in completed_steps:
        lines.append(f"  ✓ Step {s['step_order']}: {s['text']} (DONE)")
    for s in pending_steps[:3]:
        lines.append(f"  ○ Step {s['step_order']}: {s['text']} (TODO)")
    
    next_step = pending_steps[0] if pending_steps else None
    
    lines.append("")
    lines.append(
        f"IMPORTANT: You are helping the user achieve: {goal.title}. "
        f"Progress: {len(completed_steps)}/{len(steps)} steps done."
    )
    
    if next_step:
        lines.append(
            f"Focus on helping them complete the next step: {next_step['text']}. "
            f"Ask about their progress on this step. "
            f"Offer practical tips and encouragement."
        )
    else:
        lines.append(
            "All current steps are done! Help them add more steps or create a new goal."
        )
    
    return "\n".join(lines)


def _handle_goal_commands(message: str) -> str | None:
    m = (message or "").strip()
    lower = m.lower()

    # Create goal
    set_goal = re.search(r"\b(set goal to|new goal|my main goal is|i want to|i need to)\s+(.+)$", lower, flags=re.IGNORECASE)
    if set_goal:
        title = set_goal.group(2).strip(" .")
        if not title:
            return "What would you like to set as your goal?"
        UserGoal.objects.filter(is_active=True).update(is_active=False)
        goal = UserGoal.objects.create(title=title, is_active=True, status="active")
        return (
            f"Goal created: '{title}' 🎯\n\n"
            f"Now let's break it down into steps. Tell me the first step, or say 'add step: [step description]'."
        )

    active_goal = _get_active_goal()

    # Add step
    add_step = re.search(r"\b(add step|add goal step|step\s*\d*[:\-]?)\s+(.+)$", lower, flags=re.IGNORECASE)
    if add_step:
        if not active_goal:
            return "No active goal yet. Set a goal first with 'I want to [goal]'."
        text = add_step.group(2).strip(" .")
        if not text:
            return "Please describe the step you want to add."
        next_order = (active_goal.steps.order_by("-step_order").values_list("step_order", flat=True).first() or 0) + 1
        GoalStep.objects.create(goal=active_goal, text=text, step_order=next_order, is_done=False)
        return f"✅ Added step {next_order}: '{text}' to goal '{active_goal.title}'."

    # Done step
    done_step = re.search(r"\b(done step|complete step|finished step|did step)\s+(\d+)\b", lower, flags=re.IGNORECASE)
    if done_step:
        if not active_goal:
            return "No active goal yet."
        idx = int(done_step.group(2))
        step = active_goal.steps.filter(step_order=idx).first()
        if not step:
            return f"I could not find step {idx}."
        step.is_done = True
        step.save(update_fields=["is_done"])
        pending = active_goal.steps.filter(is_done=False).count()
        if pending == 0:
            return f"🎉 Amazing! You completed ALL steps for '{active_goal.title}'! Want to add more steps or set a new goal?"
        return f"✅ Marked step {idx} as done. {pending} step{'s' if pending != 1 else ''} remaining. Keep going!"

    # Status
    if re.search(r"\b(goal status|what('s| is) my goal|how('s| is) my goal|what('s| is) next|next step|goal progress|my goal)\b", lower):
        if not active_goal:
            return "No active goal yet. Tell me what you want to achieve and I'll help you plan it! 💡"
        next_step = active_goal.steps.filter(is_done=False).order_by("step_order").first()
        total = active_goal.steps.count()
        done = active_goal.steps.filter(is_done=True).count()
        progress = (done / total * 100) if total > 0 else 0
        if next_step:
            return (
                f"🎯 Goal: {active_goal.title}\n"
                f"📊 Progress: {done}/{total} steps done ({progress:.0f}%)\n"
                f"➡️ Next step: {next_step.text}\n\n"
                f"Keep pushing! Small steps lead to big wins. 💪"
            )
        return f"🎉 Goal '{active_goal.title}' - All steps completed! Amazing work! Want to set a new goal?"

    # Complete goal
    if re.search(r"\b(complete goal|goal completed|finish goal|achieved my goal)\b", lower):
        if not active_goal:
            return "No active goal to complete."
        active_goal.status = "completed"
        active_goal.is_active = False
        active_goal.save(update_fields=["status", "is_active", "updated_at"])
        return f"🎉🏆 Goal completed: '{active_goal.title}'! You're amazing! What's your next goal?"

    # Delete/cancel goal
    if re.search(r"\b(delete goal|cancel goal|remove goal|abandon goal)\b", lower):
        if not active_goal:
            return "No active goal to delete."
        title = active_goal.title
        active_goal.delete()
        return f"Goal '{title}' removed. What would you like to focus on instead?"

    return None


def _handle_habit_commands(message: str) -> str | None:
    """Handle habit-related voice/text commands."""
    m = (message or "").strip()
    lower = m.lower()
    
    # Create new habit
    create_match = re.search(
        r"\b(create|add|new|start|track)\s+(a\s+)?habit\s+(to|of|called|named)?\s*(.+)$",
        lower,
        flags=re.IGNORECASE
    )
    if create_match:
        habit_name = create_match.group(4).strip() if create_match.group(4) else ""
        if not habit_name:
            return "What habit would you like to create? For example: 'create a habit of morning exercise'"
        
        # Check if habit already exists
        existing = HabitTracker.objects.filter(name__iexact=habit_name, is_active=True).first()
        if existing:
            return f"You already have a habit called '{existing.name}'. Keep it up!"
        
        HabitTracker.objects.create(name=habit_name, frequency='daily')
        return f"Great! I've created a new habit: '{habit_name}'. Mark it complete each day to build your streak!"
    
    # Complete/Log habit
    complete_match = re.search(
        r"\b(complete|done|finished|did|log|check)\s+(my\s+)?habit\s+(called|named|of)?\s*(.+)$",
        lower,
        flags=re.IGNORECASE
    )
    if complete_match:
        habit_name = complete_match.group(4).strip() if complete_match.group(4) else ""
        if not habit_name:
            return "Which habit would you like to complete?"
        
        habit = HabitTracker.objects.filter(name__icontains=habit_name, is_active=True).first()
        
        if not habit:
            available = list(HabitTracker.objects.filter(is_active=True).values_list('name', flat=True)[:5])
            if available:
                return f"I couldn't find '{habit_name}'. Your habits: {', '.join(available)}"
            return "You don't have any habits yet. Say 'create a habit of ...' to start!"
        
        today = timezone.now().date()
        log, created = HabitLog.objects.get_or_create(
            habit=habit,
            date=today,
            defaults={'completed': True}
        )
        
        if not created and not log.completed:
            log.completed = True
            log.save()
            return f"Awesome! Marked '{habit.name}' as complete for today. Current streak: {habit.current_streak} days!"
        elif not created:
            return f"'{habit.name}' is already marked complete for today. Current streak: {habit.current_streak} days!"
        
        return f"Awesome! Marked '{habit.name}' as complete for today. Current streak: {habit.current_streak} days!"
    
    # Check habit status
    status_match = re.search(
        r"\b(how('s| is)|status|show)\s+(my\s+)?habit\s+(called|named|of)?\s*(.+)$",
        lower,
        flags=re.IGNORECASE
    )
    if status_match:
        habit_name = status_match.group(5).strip() if status_match.group(5) else ""
        if not habit_name:
            return "Which habit would you like to check?"
        
        habit = HabitTracker.objects.filter(name__icontains=habit_name, is_active=True).first()
        
        if not habit:
            return f"I couldn't find a habit called '{habit_name}'."
        
        today = timezone.now().date()
        today_log = habit.logs.filter(date=today).first()
        completed_text = "completed today ✓" if (today_log and today_log.completed) else "not completed yet today"
        
        return f"'{habit.name}' - {completed_text}. Current streak: {habit.current_streak} days. Best streak: {habit.best_streak} days. Completion rate: {habit.completion_rate}%"
    
    # List all habits
    if re.search(r"\b(my\s+habits|list habits|show habits|all habits)\b", lower):
        habits = HabitTracker.objects.filter(is_active=True).order_by('-created_at')
        
        if not habits:
            return "You don't have any habits yet. Say 'create a habit of ...' to start tracking!"
        
        habit_list = []
        for h in habits:
            today = timezone.now().date()
            today_log = h.logs.filter(date=today).first()
            status = "✓" if (today_log and today_log.completed) else "○"
            habit_list.append(f"{status} {h.name} (streak: {h.current_streak} days)")
        
        return "Your habits:\n" + "\n".join(habit_list)
    
    # Delete habit
    delete_match = re.search(
        r"\b(delete|remove|stop)\s+(my\s+)?habit\s+(called|named|of)?\s*(.+)$",
        lower,
        flags=re.IGNORECASE
    )
    if delete_match:
        habit_name = delete_match.group(4).strip() if delete_match.group(4) else ""
        if not habit_name:
            return "Which habit would you like to delete?"
        
        habit = HabitTracker.objects.filter(name__icontains=habit_name, is_active=True).first()
        
        if not habit:
            return f"I couldn't find a habit called '{habit_name}'."
        
        habit.is_active = False
        habit.save()
        return f"Removed '{habit.name}' from your habits."
    
    return None


def _extract_profile_updates(message: str, profile: UserProfile) -> list[str]:
    updates = []
    text = (message or "").strip()

    m_name = re.search(r"\bmy name is\s+([A-Za-z][A-Za-z\s\-']+)$", text, flags=re.IGNORECASE)
    if m_name:
        name = m_name.group(1).strip(" .")
        if name and profile.display_name != name:
            profile.display_name = name
            updates.append(f"name={name}")

    m_goal = re.search(r"\b(my goal is|my goals are|i want to)\s+(.+)$", text, flags=re.IGNORECASE)
    if m_goal:
        goal = m_goal.group(2).strip(" .")
        if goal:
            existing = profile.habit_goals or ""
            if goal.lower() not in existing.lower():
                profile.habit_goals = (existing + "\n" + goal).strip()
                updates.append("habit_goal")

    m_pref = re.search(r"\b(i prefer|i like responses that are)\s+(.+)$", text, flags=re.IGNORECASE)
    if m_pref:
        pref = m_pref.group(2).strip(" .")
        if pref:
            existing = profile.preferences or ""
            if pref.lower() not in existing.lower():
                profile.preferences = (existing + "\n" + pref).strip()
                updates.append("preference")

    if updates:
        profile.save(update_fields=["display_name", "habit_goals", "preferences", "updated_at"])
    return updates


def _detect_mood(message: str) -> tuple[str, str]:
    """Detect user mood from text using comprehensive keyword analysis."""
    text = (message or "").lower()
    
    # Crisis detection (highest priority)
    crisis_markers = [
        "kill myself", "end my life", "want to die", "suicide", "suicidal",
        "self harm", "self-harm", "hurt myself", "better off dead",
        "can't go on", "cant go on", "cannot go on", "no reason to live",
        "don't want to live", "dont want to live", "ending it all",
        "want to end it all", "life is not worth living",
    ]
    if any(m in text for m in crisis_markers):
        return "crisis", "high"
    
    # Comprehensive mood lexicon with expanded keywords
    mood_lexicon = {
        "stressed": [
            "stressed", "overwhelmed", "burned out", "burnt out", "pressure",
            "anxious", "anxiety", "panic", "worried sick", "can't cope",
            "cant cope", "too much", "breaking point", "snapping",
            "can't handle", "cant handle", "losing control",
        ],
        "worried": [
            "worried", "nervous", "on edge", "uneasy", "scared about",
            "afraid that", "concerned", "apprehensive", "what if",
            "fear that", "dreading", "dread", "tense",
        ],
        "sad": [
            "sad", "down", "depressed", "unhappy", "heartbroken", "blue",
            "grieving", "cry", "crying", "tears", "hopeless", "miserable",
            "empty inside", "feel empty", "nothing matters", "worthless",
            "lost everything", "missing someone", "miss you", "miss him",
            "miss her", "feeling low", "so lonely", "hurt", "hurts",
        ],
        "lonely": [
            "lonely", "alone", "isolated", "no one cares", "nobody understands",
            "no friends", "don't have anyone", "dont have anyone", "by myself",
            "all alone", "no one to talk to", "feel disconnected", "left out",
            "forgotten", "invisible", "no one loves me", "nobody loves me",
        ],
        "angry": [
            "angry", "mad", "frustrated", "annoyed", "furious", "rage",
            "pissed", "irritated", "hate this", "so annoying", "infuriating",
            "can't stand", "cant stand", "sick of", "fed up", "outraged",
            "livid", "seething", "unfair", "not fair", "disgusted",
        ],
        "happy": [
            "happy", "great", "awesome", "excited", "good day", "fantastic",
            "joy", "wonderful", "amazing", "love this", "feeling good",
            "feeling great", "thrilled", "delighted", "cheerful", "glad",
            "so pleased", "over the moon", "on top of the world",
            "having a blast", "living my best life",
        ],
        "grateful": [
            "grateful", "thankful", "blessed", "appreciate", "thanks",
            "thank you", "so grateful", "really appreciate", "gratitude",
            "lucky to have", "fortunate", "blessing",
        ],
        "tired": [
            "tired", "exhausted", "sleepy", "drained", "burnt out energy",
            "no energy", "fatigued", "worn out", "can't keep my eyes open",
            "cant sleep", "insomnia", "running on empty", "dead tired",
            "completely exhausted", "need rest",
        ],
        "confused": [
            "confused", "not sure", "unclear", "don't understand", "lost",
            "what does", "how do i", "help me understand", "confusing",
            "makes no sense", "puzzled", "baffled", "clueless",
        ],
        "hopeful": [
            "hopeful", "optimistic", "looking forward", "excited about future",
            "things will get better", "it will work out", "positive",
            "bright future", "good things coming", "can't wait",
        ],
        "scared": [
            "scared", "terrified", "fear", "afraid", "frightened", "panic",
            "creepy", "haunted", "nightmare", "can't stop thinking about",
            "phobia", "paranoid",
        ],
    }
    
    # Score each mood
    best_mood = "neutral"
    best_score = 0
    
    for mood, keywords in mood_lexicon.items():
        score = 0
        for keyword in keywords:
            if keyword in text:
                # Longer phrases get higher weight
                weight = len(keyword.split())
                score += weight
        
        if score > best_score:
            best_score = score
            best_mood = mood
    
    # Determine intensity
    if best_score == 0:
        return "neutral", "low"
    elif best_score <= 2:
        return best_mood, "low"
    elif best_score <= 5:
        return best_mood, "medium"
    else:
        return best_mood, "high"


def _mood_response_guidance(mood: str, intensity: str) -> str:
    if mood == "crisis":
        return (
            "CRITICAL: The user’s words may indicate severe distress or self-harm risk. "
            "Respond with calm warmth in a few sentences. Do not shame or debate their feelings. "
            "Do not give medical advice or instructions about self-harm. "
            "Encourage contacting local emergency services if they are in immediate danger, "
            "and mention the 988 Suicide & Crisis Lifeline (US) or equivalent local crisis lines. "
            "Suggest reaching a trusted person when possible."
        )
    if mood in {"stressed", "worried", "sad", "lonely", "angry", "tired"}:
        return (
            f"User mood appears {mood} (intensity: {intensity}). "
            "Lead with empathy and validation in one short sentence, then offer one or two gentle, practical options. "
            "Avoid toxic positivity; do not minimize their experience."
        )
    if mood in {"happy", "grateful"}:
        return (
            f"User mood appears positive ({mood}, {intensity}). "
            "Match their energy warmly; you can briefly celebrate with them and offer a helpful next step if relevant."
        )
    if mood in {"confused"}:
        return "User may be confused. Explain clearly in small steps; invite a clarifying question if needed."
    return "No strong mood signal. Keep response natural, kind, and helpful."


def _build_profile_context(profile: UserProfile) -> str:
    return (
        "User profile context:\n"
        f"- Name: {profile.display_name or 'unknown'}\n"
        f"- Habit goals: {profile.habit_goals or 'none'}\n"
        f"- Preferences: {profile.preferences or 'none'}"
    )


def _proactive_suggestion(mood: str, profile: UserProfile, user_message: str) -> str | None:
    lower = (user_message or "").lower()
    if mood == "crisis":
        return None
    active_goal = _get_active_goal()
    if active_goal:
        next_step = active_goal.steps.filter(is_done=False).order_by("step_order").first()
        if next_step and mood not in {"sad", "lonely", "worried"}:
            return f"To move your goal '{active_goal.title}' forward, next step is: {next_step.text}"
    if mood == "stressed":
        return "If you want, I can set a 5-minute breathing timer right now."
    if mood == "worried":
        return "We can name one small worry and one tiny next step, or set a short grounding timer."
    if mood == "lonely":
        return "If it helps, we can plan one low-pressure way to connect with someone today."
    if mood == "sad":
        return "Want to try a 2-minute self-kindness check-in, or keep talking it through?"
    if mood == "tired":
        return "Want me to set a short 20-minute focus timer and a break reminder?"
    if "plan" in lower or "schedule" in lower:
        return "I can help break this into a simple step-by-step plan."
    if profile.habit_goals and "habit" in profile.habit_goals.lower():
        return "Would you like a reminder schedule to stay consistent with your habit goals?"
    return None


def _emotional_recent_context(conversation) -> str:
    """Short summary of recent mood logs so the model can track emotional continuity."""
    rows = list(
        MoodLog.objects.filter(conversation=conversation)
        .order_by("-created_at")
        .values("mood", "intensity")[:5]
    )
    if not rows:
        return "Recent emotional context: no mood notes in this chat yet."
    parts = [f"{r['mood']} ({r['intensity']})" for r in reversed(rows)]
    return "Recent emotional tone in this chat (oldest→newest): " + " → ".join(parts)


def _handle_auto_mode_command(message: str, profile: UserProfile) -> str | None:
    m = (message or "").strip().lower()
    if re.search(r"\b(auto mode on|enable auto mode|turn on auto mode)\b", m):
        if not profile.auto_agent_mode:
            profile.auto_agent_mode = True
            profile.save(update_fields=["auto_agent_mode", "updated_at"])
        return "Auto task mode is now ON. I will perform supported tasks automatically."
    if re.search(r"\b(auto mode off|disable auto mode|turn off auto mode)\b", m):
        if profile.auto_agent_mode:
            profile.auto_agent_mode = False
            profile.save(update_fields=["auto_agent_mode", "updated_at"])
        return "Auto task mode is now OFF. I will ask more explicitly before task actions."
    if re.search(r"\b(auto mode status|is auto mode on)\b", m):
        return f"Auto task mode is {'ON' if profile.auto_agent_mode else 'OFF'}."
    return None


def _infer_auto_action(message: str) -> dict | None:
    m = (message or "").strip().lower()

    # --- NEW: Direct site matching for voice commands ---
    # This allows opening sites by just saying their name (e.g., "YouTube")
    direct_sites = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "gmail": "https://mail.google.com",
        "chatgpt": "https://chatgpt.com",
        "github": "https://github.com",
        "whatsapp": "https://web.whatsapp.com",
        "linkedin": "https://www.linkedin.com",
        "twitter": "https://x.com",
        "x": "https://x.com",
        "instagram": "https://www.instagram.com",
        "facebook": "https://www.facebook.com",
        "netflix": "https://www.netflix.com",
        "spotify": "https://open.spotify.com",
        "reddit": "https://www.reddit.com",
        "amazon": "https://www.amazon.in",
    }
    
    # Check for exact match (ignoring punctuation like "YouTube.")
    clean_m = re.sub(r'[^\w\s]', '', m).strip()
    if clean_m in direct_sites:
        return {"response": f"Opening {clean_m.title()}.", "action": {"type": "open_url", "url": direct_sites[clean_m]}}

    # --- Handle "Play Song" commands directly ---
    # This allows: "play song Baby", "play music", "play song on youtube"
    song_patterns = [
        r"play\s+(?:song|music|the)?\s*(.+?)\s*(?:on\s+youtube)?$",
        r"search\s+(?:song|music|for)?\s*(.+?)\s*(?:on\s+youtube)?$",
    ]
    
    for pattern in song_patterns:
        match = re.search(pattern, m)
        if match:
            query = match.group(1).strip()
            # Filter out noise words if the query is just "play song"
            if query and query.lower() not in ["song", "music", "the", "a"]:
                # Ensure we search for the specific query on YouTube
                url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
                return {"response": f"Playing {query} on YouTube 🎵", "action": {"type": "open_url", "url": url}}

    # Timer
    timer_seconds = _extract_timer_seconds(m)
    if timer_seconds:
        if timer_seconds % 60 == 0:
            minutes = timer_seconds // 60
            reply = f"Timer set for {minutes} minute{'s' if minutes != 1 else ''}."
            label = f"{minutes}-minute timer"
        else:
            reply = f"Timer set for {timer_seconds} second{'s' if timer_seconds != 1 else ''}."
            label = f"{timer_seconds}-second timer"
        return {"response": reply, "action": {"type": "set_timer", "seconds": timer_seconds, "label": label}}

    if _is_cancel_timer_request(m):
        return {"response": "Okay, canceling all active timers.", "action": {"type": "cancel_timers"}}

    # Auto open known sites with looser phrasing
    if "youtube" in m and re.search(r"\b(open|watch|play|go to|start)\b", m):
        q = _extract_youtube_query(m)
        if q:
            url = f"https://www.youtube.com/results?search_query={quote_plus(q)}"
            return {"response": f"Searching YouTube for {q}.", "action": {"type": "open_url", "url": url}}
        return {"response": "Opening YouTube.", "action": {"type": "open_url", "url": "https://www.youtube.com"}}

    if "google" in m and re.search(r"\b(search|find|look up)\b", m):
        q = _extract_google_search_query(m)
        if q:
            url = f"https://www.google.com/search?q={quote_plus(q)}"
            return {"response": f"Searching Google for {q}.", "action": {"type": "open_url", "url": url}}

    if "amazon" in m and re.search(r"\b(search|find|buy|look)\b", m):
        q = _extract_amazon_query(m)
        if q:
            url = f"https://www.amazon.in/s?k={quote_plus(q)}"
            return {"response": f"Searching Amazon for {q}.", "action": {"type": "open_url", "url": url}}
        return {"response": "Opening Amazon.", "action": {"type": "open_url", "url": "https://www.amazon.in"}}

    if ("map" in m or "maps" in m or "navigate" in m) and re.search(r"\b(open|go|find|navigate|route)\b", m):
        mq = _extract_maps_query(m)
        if mq:
            place, is_nav = mq
            if place:
                if is_nav:
                    url = f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(place)}"
                    return {"response": f"Starting navigation to {place}.", "action": {"type": "open_url", "url": url}}
                url = f"https://www.google.com/maps/search/{quote_plus(place)}"
                return {"response": f"Opening maps for {place}.", "action": {"type": "open_url", "url": url}}

    if "gmail" in m and re.search(r"\b(open|send|email|mail)\b", m):
        return {"response": "Opening Gmail.", "action": {"type": "open_url", "url": "https://mail.google.com"}}

    if re.search(r"\b(open|launch|start)\b", m):
        lt = _extract_open_target(m)
        if lt:
            inferred_open = _action_for_open_target(lt)
            if inferred_open:
                return inferred_open

    return None


_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "for", "of", "in", "on", "is", "are",
    "it", "this", "that", "with", "as", "be", "i", "you", "my", "me", "we", "our",
    "from", "at", "by", "about", "can", "could", "should", "would", "please",
}


def _tokenize_keywords(text: str, limit: int = 6) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9\-']{2,}", (text or "").lower())
    out = []
    seen = set()
    for w in words:
        if w in _STOPWORDS:
            continue
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= limit:
            break
    return out


def _is_follow_up_message(message: str) -> bool:
    m = (message or "").strip().lower()
    if len(m) <= 24:
        return True
    follow_up_markers = [
        "what about", "and ", "also", "then", "that one", "this one",
        "can you", "could you", "why", "how", "yes", "no", "ok", "okay",
        "do that", "continue", "go on",
    ]
    return any(marker in m for marker in follow_up_markers)


def _assistant_has_open_question(history_rows: list[dict]) -> bool:
    if not history_rows:
        return False
    last_reply = (history_rows[-1].get("response") or "").strip()
    if not last_reply:
        return False
    return last_reply.endswith("?")


def _build_context_awareness_message(
    conversation: Conversation,
    history_rows: list[dict],
    user_message: str,
) -> str:
    recent_user = [r.get("message", "") for r in history_rows[-4:]]
    recent_keywords = []
    for msg in recent_user:
        recent_keywords.extend(_tokenize_keywords(msg, limit=4))
    dedup_keywords = []
    seen = set()
    for k in recent_keywords:
        if k not in seen:
            seen.add(k)
            dedup_keywords.append(k)
    dedup_keywords = dedup_keywords[:10]

    lines = [
        "Context awareness guidance:",
        f"- Current topic hint: {conversation.current_topic or 'unknown'}",
        f"- Running summary: {conversation.running_summary or 'none'}",
        f"- Follow-up likely: {'yes' if _is_follow_up_message(user_message) else 'no'}",
        f"- Assistant asked unresolved question previously: {'yes' if _assistant_has_open_question(history_rows) else 'no'}",
        f"- Recent user keywords: {', '.join(dedup_keywords) if dedup_keywords else 'none'}",
        "- Maintain continuity. Avoid restarting or repeating prior introductions.",
        "- If user follow-up is short/ambiguous, interpret it using recent context first.",
    ]
    return "\n".join(lines)


def _update_conversation_context(
    conversation: Conversation,
    history_rows: list[dict],
    user_message: str,
    reply: str,
) -> None:
    recent_user = [r.get("message", "") for r in history_rows[-4:]] + [user_message]
    all_text = " ".join(recent_user)
    topic_keywords = _tokenize_keywords(all_text, limit=3)
    new_topic = ", ".join(topic_keywords)

    previous_summary = (conversation.running_summary or "").strip()
    new_summary_chunk = f"User: {user_message[:120]} | Assistant: {(reply or '')[:120]}"
    if previous_summary:
        merged = previous_summary + " || " + new_summary_chunk
    else:
        merged = new_summary_chunk
    merged = _truncate(merged, 900)

    updates = []
    if conversation.current_topic != new_topic:
        conversation.current_topic = new_topic
        updates.append("current_topic")
    if conversation.running_summary != merged:
        conversation.running_summary = merged
        updates.append("running_summary")
    if updates:
        conversation.save(update_fields=updates)


def _set_personal_memory(key: str, value: str, conversation: Conversation | None = None) -> None:
    clean_key = (key or "").strip().lower()
    clean_value = (value or "").strip()
    if not clean_key or not clean_value:
        return
    PersonalMemory.objects.filter(key=clean_key).delete()
    PersonalMemory.objects.create(
        key=clean_key,
        value=clean_value,
        source_conversation=conversation,
    )


def _append_personal_memory(key: str, value: str, conversation: Conversation | None = None) -> None:
    clean_key = (key or "").strip().lower()
    clean_value = (value or "").strip()
    if not clean_key or not clean_value:
        return
    exists = PersonalMemory.objects.filter(key=clean_key, value__iexact=clean_value).exists()
    if not exists:
        PersonalMemory.objects.create(
            key=clean_key,
            value=clean_value,
            source_conversation=conversation,
        )


def _extract_personal_memories(message: str, conversation: Conversation) -> list[str]:
    text = (message or "").strip()
    updates = []

    patterns_single = [
        (r"\bmy name is\s+([A-Za-z][A-Za-z\s\-']+)$", "name"),
        (r"\bi live in\s+([A-Za-z0-9\s,\-']+)$", "location"),
        (r"\bi am from\s+([A-Za-z0-9\s,\-']+)$", "location"),
        (r"\bi work as\s+([A-Za-z0-9\s,\-']+)$", "profession"),
        (r"\bmy job is\s+([A-Za-z0-9\s,\-']+)$", "profession"),
    ]

    for pattern, key in patterns_single:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            value = m.group(1).strip(" .")
            if value:
                _set_personal_memory(key, value, conversation)
                updates.append(f"{key}: {value}")

    like_match = re.search(r"\b(i like|i love)\s+(.+)$", text, flags=re.IGNORECASE)
    if like_match:
        like_value = like_match.group(2).strip(" .")
        if like_value and len(like_value) <= 120:
            _append_personal_memory("likes", like_value, conversation)
            updates.append(f"likes: {like_value}")

    remember_match = re.search(r"\bremember that\s+(.+)$", text, flags=re.IGNORECASE)
    if remember_match:
        note = remember_match.group(1).strip(" .")
        if note:
            _append_personal_memory("notes", note, conversation)
            updates.append(f"note: {note}")

    return updates


def _detect_goal_opportunity(message: str) -> str | None:
    """Detect if user message suggests a goal they want to achieve."""
    text = (message or "").lower()
    
    # Goal indicators
    goal_phrases = [
        (r"i want to\s+(.+)", "What's something you'd like to achieve? I can help you create a goal and track your progress!"),
        (r"i need to\s+(.+)", "It sounds like you have something important to do. Want me to help you break it into manageable steps?"),
        (r"i should\s+(.+)", "That sounds meaningful. Would you like to set it as a goal with steps to track your progress?"),
        (r"my goal is\s+(.+)", None),  # Already handled
        (r"i'm trying to\s+(.+)", "Trying is the first step! Want me to help you turn that into a concrete plan with trackable steps?"),
        (r"i'd like to\s+(.+)", "That's a great aspiration! Want to make it a real goal with actionable steps?"),
        (r"how can i\s+(.+)", "Great question! I can help you create a step-by-step plan. Want to set this up as a goal?"),
        (r"help me\s+(.+)", "I'd love to help! Let's break this down into manageable steps. Want to create a goal for it?"),
    ]
    
    for pattern, suggestion in goal_phrases:
        if re.search(pattern, text):
            return suggestion
    
    return None


def _handle_media_command(message: str) -> dict | None:
    """Handle media-related commands: Play music/video, Open platform, Volume."""
    m = (message or "").strip()
    lower = m.lower()

    # 1. Play Song / Music
    song_match = re.search(r"\b(play|listen to|search)\s+(?:song|music|track)\s+(.+)$", lower, flags=re.IGNORECASE)
    if song_match:
        query = song_match.group(2).strip()
        # Check for platform specific
        if "spotify" in query:
            url = f"https://open.spotify.com/search/{quote_plus(query)}"
            return {"response": f"🎵 Searching Spotify for {query}.", "action": {"type": "open_url", "url": url}}
        url = f"https://www.youtube.com/results?search_query={quote_plus(query + ' song')}"
        return {"response": f"🎵 Playing '{query}' on YouTube.", "action": {"type": "open_url", "url": url}}

    # 2. Play Video / Movie / Show
    video_match = re.search(r"\b(play|watch|search)\s+(?:video|movie|show|episode)\s+(.+)$", lower, flags=re.IGNORECASE)
    if video_match:
        query = video_match.group(2).strip()
        if "netflix" in query:
            url = f"https://www.netflix.com/search?q={quote_plus(query)}"
            return {"response": f"🎬 Searching Netflix for {query}.", "action": {"type": "open_url", "url": url}}
        url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        return {"response": f"🎬 Playing '{query}' on YouTube.", "action": {"type": "open_url", "url": url}}

    # 3. Open Specific Platform
    platform_match = re.search(r"\b(open|go to|launch)\s+(spotify|netflix|youtube|prime video|hulu|amazon music|soundcloud)", lower, flags=re.IGNORECASE)
    if platform_match:
        platform = platform_match.group(2).strip()
        urls = {
            "spotify": "https://open.spotify.com",
            "netflix": "https://www.netflix.com",
            "youtube": "https://www.youtube.com",
            "prime video": "https://www.primevideo.com",
            "hulu": "https://www.hulu.com",
            "amazon music": "https://music.amazon.in",
            "soundcloud": "https://soundcloud.com"
        }
        if platform in urls:
            return {"response": f"📺 Opening {platform.title()}.", "action": {"type": "open_url", "url": urls[platform]}}

    # 4. Volume Control (Frontend handles this via 'adjust_volume' action)
    vol_up = re.search(r"\b(volume|sound|voice)\s*(up|louder|increase|more)", lower, flags=re.IGNORECASE)
    if vol_up:
        return {"response": "🔊 Turning up the volume.", "action": {"type": "adjust_volume", "value": "up"}}
    
    vol_down = re.search(r"\b(volume|sound|voice)\s*(down|quieter|decrease|less|low)", lower, flags=re.IGNORECASE)
    if vol_down:
        return {"response": "🔉 Turning down the volume.", "action": {"type": "adjust_volume", "value": "down"}}
        
    mute = re.search(r"\b(mute|shut up|stop talking|be quiet|silence)\b", lower, flags=re.IGNORECASE)
    if mute:
        return {"response": "🔇 Muting the assistant.", "action": {"type": "adjust_volume", "value": "mute"}}

    unmute = re.search(r"\b(unmute|speak up|talk)\b", lower, flags=re.IGNORECASE)
    if unmute:
        return {"response": "🔊 Unmuted.", "action": {"type": "adjust_volume", "value": "unmute"}}

    return None


def _handle_student_command(message: str) -> dict | None:
    """Handle student-related commands: subjects, assignments, exams."""
    m = (message or "").strip()
    lower = m.lower()

    # Add Subject
    subject_match = re.search(r"\b(add|create|new)\s+subject\s+(.+)$", lower, flags=re.IGNORECASE)
    if subject_match:
        name = subject_match.group(2).strip()
        Subject.objects.get_or_create(name__iexact=name, defaults={'name': name})
        return {"response": f"✅ Subject added: '{name}'.", "action": {"type": "refresh_student"}}

    # Add Assignment
    assign_match = re.search(r"\b(add|create|new)\s+(assignment|homework|project)\s+(?:for\s+)?(.+?)\s+(?:on\s+|in\s+|about\s+|due\s+|to\s+)?(?:do\s+)?(.+)$", lower, flags=re.IGNORECASE)
    if assign_match:
        subj_name = assign_match.group(3).strip()
        title = assign_match.group(4).strip()
        
        subject = Subject.objects.filter(name__iexact=subj_name).first()
        if subject:
            Assignment.objects.create(subject=subject, title=title)
            return {"response": f"✅ Assignment '{title}' added for {subject.name}.", "action": {"type": "refresh_student"}}
        else:
            return {"response": f"Subject '{subj_name}' not found. Please add the subject first."}

    # Add Exam
    exam_match = re.search(r"\b(add|create|new)\s+(exam|test|quiz)\s+(?:for\s+)?(.+?)\s+(?:on\s+|at\s+|in\s+)?(.+)$", lower, flags=re.IGNORECASE)
    if exam_match:
        subj_name = exam_match.group(3).strip()
        date_str = exam_match.group(4).strip()
        # Attempt to parse date or just store it
        subject = Subject.objects.filter(name__iexact=subj_name).first()
        Exam.objects.create(
            subject=subject,
            title=f"{subj_name} Exam",
            exam_date=timezone.now() + timezone.timedelta(days=7), # Placeholder date
        )
        return {"response": f"📅 Exam added for {subj_name}.", "action": {"type": "refresh_student"}}

    # List Student Data
    if re.search(r"\b(my\s+)?(subjects|classes)\b", lower):
        subjects = list(Subject.objects.values_list('name', flat=True))
        if subjects:
            return {"response": f"📚 Your subjects are: {', '.join(subjects)}.", "action": {"type": "refresh_student"}}
        return {"response": "You haven't added any subjects yet."}

    if re.search(r"\b(my\s+)?(assignments|homework|pending)\b", lower):
        count = Assignment.objects.filter(is_completed=False).count()
        if count > 0:
            items = list(Assignment.objects.filter(is_completed=False).values_list('title', 'subject__name'))
            msg = "\n".join([f"- {t} ({s})" for t, s in items[:5]])
            return {"response": f"📝 You have {count} pending assignments:\n{msg}", "action": {"type": "refresh_student"}}
        return {"response": "🎉 No pending assignments! You're all caught up."}

    # Complete Assignment
    complete_match = re.search(r"\b(complete|done|finish)\s+(assignment|homework)\s+(.+)$", lower, flags=re.IGNORECASE)
    if complete_match:
        title = complete_match.group(3).strip()
        assign = Assignment.objects.filter(title__icontains=title, is_completed=False).first()
        if assign:
            assign.is_completed = True
            assign.save()
            return {"response": f"✅ Marked '{assign.title}' as complete!", "action": {"type": "refresh_student"}}
        return {"response": f"Assignment '{title}' not found."}

    return None


def _handle_task_command(message: str) -> dict | None:
    """Handle task-related commands: add, list, complete, delete."""
    m = (message or "").strip()
    lower = m.lower()

    # Add Task
    add_match = re.search(r"\b(add|create|new)\s+(?:task|todo)\s*(?::|to)?\s*(.+)$", lower, flags=re.IGNORECASE)
    if add_match:
        title = add_match.group(2).strip()
        if not title:
            return None
        Task.objects.create(title=title)
        return {"response": f"✅ Task added: '{title}'.", "action": {"type": "refresh_tasks"}}

    # Complete Task
    complete_match = re.search(r"\b(complete|done|finish|check)\s+(?:task\s*)?(.+)$", lower, flags=re.IGNORECASE)
    if complete_match:
        query = complete_match.group(2).strip()
        task = Task.objects.filter(title__icontains=query, is_completed=False).first()
        if task:
            task.is_completed = True
            task.save()
            return {"response": f"✅ Marked '{task.title}' as complete.", "action": {"type": "refresh_tasks"}}
        return {"response": f"Task '{query}' not found or already completed."}

    # List Tasks
    if re.search(r"\b(list|show|my)\s+(tasks|todos)\b", lower):
        pending = Task.objects.filter(is_completed=False).count()
        completed = Task.objects.filter(is_completed=True).count()
        return {"response": f"📋 You have {pending} pending tasks and {completed} completed tasks.", "action": {"type": "refresh_tasks"}}

    # Delete Task
    delete_match = re.search(r"\b(delete|remove)\s+(?:task\s*)?(.+)$", lower, flags=re.IGNORECASE)
    if delete_match:
        query = delete_match.group(2).strip()
        task = Task.objects.filter(title__icontains=query).first()
        if task:
            task.delete()
            return {"response": f"🗑️ Deleted task '{task.title}'.", "action": {"type": "refresh_tasks"}}
        return {"response": f"Task '{query}' not found."}

    return None


def _get_personal_memory_lines(limit: int = 20) -> list[str]:
    rows = list(PersonalMemory.objects.all().order_by("-updated_at").values("key", "value")[:limit])
    return [f"{row['key']}: {row['value']}" for row in rows if row.get("key") and row.get("value")]


def _handle_memory_command(message: str, conversation: Conversation) -> str | None:
    m = message.strip().lower()

    if re.search(r"\bwhat do you remember about me\b", m):
        lines = _get_personal_memory_lines(limit=30)
        if not lines:
            return "I do not have personal memories yet. Tell me things like 'my name is ...' or 'I like ...'."
        return "Here is what I remember:\n- " + "\n- ".join(lines)

    if re.search(r"\bforget all (my )?memories\b", m):
        PersonalMemory.objects.all().delete()
        return "Okay, I cleared all personal memory."

    forget_key_patterns = [
        (r"\bforget my name\b", "name"),
        (r"\bforget my location\b", "location"),
        (r"\bforget where i live\b", "location"),
        (r"\bforget my profession\b", "profession"),
        (r"\bforget what i like\b", "likes"),
        (r"\bforget my notes\b", "notes"),
    ]
    for pattern, key in forget_key_patterns:
        if re.search(pattern, m):
            deleted, _ = PersonalMemory.objects.filter(key=key).delete()
            if deleted:
                return f"Okay, I forgot your {key}."
            return f"I did not have any stored {key}."
    return None


_WEATHER_CODE_DESCRIPTIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def _weather_code_to_text(code) -> str:
    try:
        code_int = int(code)
    except (TypeError, ValueError):
        return "Unknown conditions"
    return _WEATHER_CODE_DESCRIPTIONS.get(code_int, f"Weather code {code_int}")


def _extract_city_from_weather(message: str) -> str | None:
    # Common forms: "weather in London", "what's the weather in Paris today"
    msg = message.strip()
    m = re.search(r"\bweather\b.*?\bin\s+([A-Za-z\s\.\'-]+)", msg, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"\bweather\s+in\s+([A-Za-z\s\.\'-]+)", msg, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"\bweather\s+([A-Za-z\s\.\'-]+)", msg, flags=re.IGNORECASE)

    if not m:
        return None

    city = m.group(1).strip()
    city = re.split(
        r"\b(today|tomorrow|now|right now|hourly|daily|next)\b",
        city,
        flags=re.IGNORECASE,
    )[0].strip(" ,.")
    return city or None


def _wants_tomorrow_weather(message: str) -> bool:
    return bool(re.search(r"\b(tomorrow)\b", message, flags=re.IGNORECASE))


def _temperature_unit_from_message(message: str) -> str:
    if re.search(r"\b(fahrenheit|°f)\b", message, flags=re.IGNORECASE):
        return "fahrenheit"
    return "celsius"


def _wind_unit_from_message(message: str) -> str:
    if re.search(r"\b(fahrenheit|°f)\b", message, flags=re.IGNORECASE):
        return "mph"
    return "kmh"


def _geocode_city(city: str) -> dict | None:
    try:
        r = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={
                "name": city,
                "count": 1,
                "language": "en",
                "format": "json",
            },
            timeout=15,
        )
        data = r.json()
    except Exception:
        return None

    results = (data or {}).get("results") or []
    if not results:
        return None

    best = results[0]
    return {
        "latitude": best.get("latitude"),
        "longitude": best.get("longitude"),
        "name": best.get("name"),
        "country": best.get("country"),
    }


def _fetch_weather(
    lat: float,
    lon: float,
    *,
    temperature_unit: str,
    wind_unit: str,
) -> dict | None:
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                "timezone": "auto",
                "temperature_unit": temperature_unit,
                "windspeed_unit": wind_unit,
            },
            timeout=20,
        )
        return r.json()
    except Exception:
        return None


def _handle_weather_request(message: str) -> str:
    city = _extract_city_from_weather(message)
    if not city:
        return "Which city should I check the weather for? (Example: `weather in London`)"

    geocoded = _geocode_city(city)
    if not geocoded:
        return f"Sorry, I couldn't find location for `{city}`. Please try again with a different city name."

    lat = geocoded.get("latitude")
    lon = geocoded.get("longitude")
    if lat is None or lon is None:
        return "Sorry, I couldn't get coordinates for that location."

    temperature_unit = _temperature_unit_from_message(message)
    wind_unit = _wind_unit_from_message(message)

    data = _fetch_weather(
        float(lat),
        float(lon),
        temperature_unit=temperature_unit,
        wind_unit=wind_unit,
    )
    if not data:
        return "Sorry, I couldn't fetch the weather right now."

    display_city = geocoded.get("name") or city
    country = geocoded.get("country")
    if country:
        display_city = f"{display_city}, {country}"

    temp_unit_symbol = "°F" if temperature_unit == "fahrenheit" else "°C"
    wind_unit_label = "mph" if wind_unit == "mph" else "km/h"

    if _wants_tomorrow_weather(message):
        daily = data.get("daily") or {}
        times = daily.get("time") or []
        idx = 1 if len(times) > 1 else 0

        max_t = (daily.get("temperature_2m_max") or [None])[idx]
        min_t = (daily.get("temperature_2m_min") or [None])[idx]
        code = (daily.get("weather_code") or [None])[idx]
        desc = _weather_code_to_text(code)

        date_str = times[idx] if idx < len(times) else ""
        date_part = f" for {date_str}" if date_str else ""
        return (
            f"Weather{date_part} in {display_city}: {desc}. "
            f"High {max_t}{temp_unit_symbol}, low {min_t}{temp_unit_symbol}."
        )

    current = data.get("current") or {}
    temp = current.get("temperature_2m")
    code = current.get("weather_code")
    wind = current.get("wind_speed_10m")
    desc = _weather_code_to_text(code)

    wind_part = f", wind {wind} {wind_unit_label}" if wind is not None else ""
    return f"Right now in {display_city}: {temp}{temp_unit_symbol}, {desc}{wind_part}."


def _is_weather_request(message: str) -> bool:
    return bool(re.search(r"\bweather\b", message, flags=re.IGNORECASE))


def _is_reminder_request(message: str) -> bool:
    return bool(
        re.search(r"\b(remind|reminder|remember)\b", message, flags=re.IGNORECASE)
        or re.search(r"\b(set a reminder)\b", message, flags=re.IGNORECASE)
    )


def _extract_open_target(message: str) -> str | None:
    m = re.search(
        r"\b(?:open|launch|start)\s+(?:the\s+)?([a-z0-9\.\-\s]+)$",
        message.strip(),
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    target = m.group(1).strip().lower()
    target = re.sub(r"\b(now|please|for me)\b", "", target).strip()
    return target or None


def _normalize_app_launch_target(raw: str) -> str:
    t = (raw or "").strip().lower()
    t = re.sub(r"\b(the|a|an|please|now|for me|application|app)\b", "", t)
    return re.sub(r"\s+", " ", t).strip()


# Ordered longest-first style: first matching key wins (multi-word before short aliases).
_NATIVE_APP_SPECS: list[tuple[str, dict[str, str | None]]] = [
    ("microsoft store", {"name": "Microsoft Store", "uri": "ms-windows-store:", "fallback_url": "https://apps.microsoft.com/"}),
    ("windows store", {"name": "Microsoft Store", "uri": "ms-windows-store:", "fallback_url": "https://apps.microsoft.com/"}),
    ("snipping tool", {"name": "Snipping Tool", "uri": "ms-screenclip:", "fallback_url": None}),
    ("snip and sketch", {"name": "Snipping Tool", "uri": "ms-screenclip:", "fallback_url": None}),
    ("xbox", {"name": "Xbox", "uri": "msxbox:", "fallback_url": "https://www.xbox.com/"}),
    ("security", {"name": "Windows Security", "uri": "ms-settings:windowsdefender", "fallback_url": None}),
    ("defender", {"name": "Windows Security", "uri": "ms-settings:windowsdefender", "fallback_url": None}),
    ("calculator", {"name": "Calculator", "uri": "ms-calculator:", "fallback_url": None}),
    ("calc", {"name": "Calculator", "uri": "ms-calculator:", "fallback_url": None}),
    ("settings", {"name": "Settings", "uri": "ms-settings:", "fallback_url": None}),
    ("system settings", {"name": "Settings", "uri": "ms-settings:", "fallback_url": None}),
    ("photos", {"name": "Photos", "uri": "ms-photos:", "fallback_url": None}),
    ("alarms", {"name": "Clock", "uri": "ms-clock:", "fallback_url": None}),
    ("alarm", {"name": "Clock", "uri": "ms-clock:", "fallback_url": None}),
    ("clock", {"name": "Clock", "uri": "ms-clock:", "fallback_url": None}),
    ("camera", {"name": "Camera", "uri": "ms-camera:", "fallback_url": None}),
    ("mail", {"name": "Mail", "uri": "mailto:", "fallback_url": "https://outlook.live.com/mail/"}),
    ("email", {"name": "Mail", "uri": "mailto:", "fallback_url": "https://outlook.live.com/mail/"}),
    ("outlook", {"name": "Outlook", "uri": "outlook:", "fallback_url": "https://outlook.live.com/"}),
    ("calendar", {"name": "Calendar", "uri": "outlookcal:", "fallback_url": "https://outlook.live.com/calendar/"}),
    ("spotify", {"name": "Spotify", "uri": "spotify:", "fallback_url": "https://open.spotify.com/"}),
    ("discord", {"name": "Discord", "uri": "discord:", "fallback_url": "https://discord.com/app"}),
    ("slack", {"name": "Slack", "uri": "slack:", "fallback_url": "https://slack.com/signin"}),
    ("teams", {"name": "Microsoft Teams", "uri": "msteams:", "fallback_url": "https://teams.microsoft.com/"}),
    ("zoom", {"name": "Zoom", "uri": "zoommtg:", "fallback_url": "https://zoom.us/download"}),
    ("vscode", {"name": "Visual Studio Code", "uri": "vscode:", "fallback_url": "https://code.visualstudio.com/"}),
    ("visual studio code", {"name": "Visual Studio Code", "uri": "vscode:", "fallback_url": "https://code.visualstudio.com/"}),
    ("word", {"name": "Microsoft Word", "uri": "ms-word:", "fallback_url": "https://www.office.com/launch/word"}),
    ("excel", {"name": "Microsoft Excel", "uri": "ms-excel:", "fallback_url": "https://www.office.com/launch/excel"}),
    ("powerpoint", {"name": "Microsoft PowerPoint", "uri": "ms-powerpoint:", "fallback_url": "https://www.office.com/launch/powerpoint"}),
    ("edge", {"name": "Microsoft Edge", "uri": "microsoft-edge:https://www.bing.com", "fallback_url": "https://www.bing.com"}),
    ("microsoft edge", {"name": "Microsoft Edge", "uri": "microsoft-edge:https://www.bing.com", "fallback_url": "https://www.bing.com"}),
    ("store", {"name": "Microsoft Store", "uri": "ms-windows-store:", "fallback_url": "https://apps.microsoft.com/"}),
]


def _resolve_native_app(target: str) -> dict[str, str | None] | None:
    q = _normalize_app_launch_target(target)
    if not q:
        return None
    for key, spec in _NATIVE_APP_SPECS:
        if q == key or q.startswith(key + " "):
            return {
                "name": spec["name"],
                "uri": spec["uri"],
                "fallback_url": spec.get("fallback_url"),
            }
    return None


def _action_for_open_target(lt: str) -> dict | None:
    """Resolve open/launch/start <target> to a URL tab or native app protocol."""
    if not lt:
        return None
    native = _resolve_native_app(lt)
    if native:
        return {
            "response": f"Opening {native['name']}.",
            "action": {
                "type": "open_app",
                "uri": native["uri"],
                "fallback_url": native.get("fallback_url"),
                "name": native["name"],
            },
        }
    open_url = _resolve_open_url(lt)
    if open_url:
        return {
            "response": f"Opening {lt}.",
            "action": {"type": "open_url", "url": open_url},
        }
    return None


def _resolve_open_url(target: str) -> str | None:
    """Resolve website name to URL. Supports common sites and any domain."""
    known = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "gmail": "https://mail.google.com",
        "chatgpt": "https://chatgpt.com",
        "github": "https://github.com",
        "whatsapp": "https://web.whatsapp.com",
        "linkedin": "https://www.linkedin.com",
        "twitter": "https://x.com",
        "x": "https://x.com",
        "instagram": "https://www.instagram.com",
        "facebook": "https://www.facebook.com",
        "netflix": "https://www.netflix.com",
        "spotify": "https://open.spotify.com",
        "discord": "https://discord.com/app",
        "reddit": "https://www.reddit.com",
        "amazon": "https://www.amazon.in",
        "flipkart": "https://www.flipkart.com",
        "stackoverflow": "https://stackoverflow.com",
        "wikipedia": "https://www.wikipedia.org",
        "yahoo": "https://www.yahoo.com",
        "bing": "https://www.bing.com",
        "duckduckgo": "https://duckduckgo.com",
        "telegram": "https://web.telegram.org",
        "slack": "https://slack.com/signin",
        "zoom": "https://zoom.us/download",
        "drive": "https://drive.google.com",
        "docs": "https://docs.google.com",
        "sheets": "https://sheets.google.com",
        "calendar": "https://calendar.google.com",
        "photos": "https://photos.google.com",
        "outlook": "https://outlook.live.com",
        "hotmail": "https://outlook.live.com",
        "pinterest": "https://www.pinterest.com",
        "twitch": "https://www.twitch.tv",
        "medium": "https://medium.com",
        "quora": "https://www.quora.com",
    }
    
    # Check known sites
    if target in known:
        return known[target]
    
    # Check if it's a direct domain (e.g., "example.com")
    if re.fullmatch(r"[a-z0-9\-]+\.[a-z]{2,}", target):
        return f"https://{target}"
    
    # Try common patterns
    domain_patterns = [
        rf"{target}\.com",
        rf"{target}\.in",
        rf"{target}\.org",
        rf"{target}\.io",
        rf"{target}\.co",
    ]
    
    for pattern in domain_patterns:
        try:
            import requests as req
            resp = req.head(f"https://{pattern}", timeout=2, allow_redirects=True)
            if resp.status_code == 200:
                return f"https://{pattern}"
        except:
            continue
    
    return None


def _extract_open_website_command(message: str) -> str | None:
    """Extract website name from open commands."""
    patterns = [
        r"\b(?:open|launch|go to|visit|navigate to|browse)\s+(?:the\s+)?(?:website\s+)?(?:called\s+)?([a-z0-9\-\.]+\.[a-z]{2,})\b",
        r"\b(?:open|launch|go to|visit)\s+([a-z]+)\b",
    ]
    
    for pattern in patterns:
        m = re.search(pattern, message.strip(), flags=re.IGNORECASE)
        if m:
            website = m.group(1).strip().lower()
            # Remove common words
            if website in ['the', 'website', 'page', 'link']:
                continue
            return website
    
    return None


def _extract_google_search_query(message: str) -> str | None:
    """Extract search query from various search command patterns."""
    patterns = [
        r"\bsearch\s+google\s+for\s+(.+)$",
        r"\bgoogle\s+(.+)$",
        r"\bsearch\s+for\s+(.+)$",
        r"\bsearch\s+(.+)$",
        r"\bfind\s+(.+)$",
        r"\blook\s+up\s+(.+)$",
        r"\bwhat\s+is\s+(.+)",
        r"\bwhat\s+are\s+(.+)",
        r"\bwho\s+is\s+(.+)",
        r"\bwho\s+are\s+(.+)",
        r"\bhow\s+to\s+(.+)",
        r"\bhow\s+does\s+(.+)",
        r"\bhow\s+can\s+i\s+(.+)",
        r"\bwhy\s+(.+)",
        r"\bwhen\s+(.+)",
        r"\bwhere\s+(.+)",
        r"\btell\s+me\s+about\s+(.+)",
        r"\bexplain\s+(.+)",
        r"\bdefine\s+(.+)",
        r"\bmeaning\s+of\s+(.+)",
    ]
    for pat in patterns:
        m = re.search(pat, message.strip(), flags=re.IGNORECASE)
        if m:
            q = m.group(1).strip()
            # Remove trailing question marks/periods
            q = q.rstrip('?.')
            return q or None
    return None


def _detect_general_search(message: str) -> str | None:
    """Detect if user wants to search something even without explicit search keywords."""
    text = message.strip().lower()
    
    # Question patterns that imply search intent
    question_patterns = [
        r"\bwhat\s+is\b",
        r"\bwhat\s+are\b",
        r"\bwho\s+is\b",
        r"\bwho\s+are\b",
        r"\bhow\s+to\b",
        r"\bhow\s+does\b",
        r"\bhow\s+do\b",
        r"\bhow\s+can\b",
        r"\bwhy\s+did\b",
        r"\bwhy\s+does\b",
        r"\bwhen\s+did\b",
        r"\bwhen\s+is\b",
        r"\bwhere\s+is\b",
        r"\bwhere\s+are\b",
    ]
    
    # Check if it's a question
    for pattern in question_patterns:
        if re.search(pattern, text):
            # Extract the question content
            question = text.strip().rstrip('?')
            return question
    
    return None


def _extract_youtube_query(message: str) -> str | None:
    """Extract YouTube search query from various command patterns including songs."""
    patterns = [
        r"\bplay\s+(.+?)\s+on\s+youtube\b",
        r"\byoutube\s+search\s+(.+)$",
        r"\bsearch\s+youtube\s+for\s+(.+)$",
        # Song/music patterns
        r"\bplay\s+(?:the\s+)?song\s+(.+)$",
        r"\bplay\s+(.+)\s+song\b",
        r"\bplay\s+(?:the\s+)?music\s+(.+)$",
        r"\bplay\s+(.+)\s+music\b",
        r"\bopen\s+song\s+(.+)$",
        r"\bsearch\s+song\s+(.+)$",
        r"\bfind\s+song\s+(.+)$",
        r"\bplay\s+(.+)$",
    ]
    for pat in patterns:
        m = re.search(pat, message.strip(), flags=re.IGNORECASE)
        if m:
            q = m.group(1).strip()
            # Filter out non-song commands
            if q.lower() in ['music', 'song', 'the song', 'the music', 'a song', 'some music']:
                continue
            return q or None
    return None


def _detect_song_request(message: str) -> str | None:
    """Detect if user wants to play/search for a song or music."""
    text = message.strip().lower()
    
    # Song/music patterns
    song_patterns = [
        r"\bplay\s+(?:some\s+)?(?:music|songs?)\b",
        r"\bplay\s+(?:a\s+)?song\b",
        r"\b(open|launch)\s+(?:some\s+)?(?:music|songs?)\b",
        r"\b(search|find)\s+(?:some\s+)?(?:music|songs?)\b",
        r"\b(listen\s+to\s+)?music\b",
        r"\bi\s+want\s+to\s+(?:listen|hear)\s+(.+)",
        r"\bplay\s+(.+)\s+by\s+(.+)",  # play [song] by [artist]
    ]
    
    for pattern in song_patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            # Extract what they want to listen to
            if m.lastindex and m.group(1) and len(m.group(1)) > 2:
                return m.group(1).strip()
            return "music"  # Default to general music search
    
    return None


def _extract_maps_query(message: str) -> tuple[str, bool] | None:
    m1 = re.search(r"\bopen\s+maps\s+for\s+(.+)$", message.strip(), flags=re.IGNORECASE)
    if m1:
        return m1.group(1).strip(), False

    m2 = re.search(r"\bnavigate\s+to\s+(.+)$", message.strip(), flags=re.IGNORECASE)
    if m2:
        return m2.group(1).strip(), True

    m3 = re.search(r"\bmaps\s+(.+)$", message.strip(), flags=re.IGNORECASE)
    if m3:
        return m3.group(1).strip(), False
    return None


def _extract_amazon_query(message: str) -> str | None:
    patterns = [
        r"\bsearch\s+on\s+amazon\s+for\s+(.+)$",
        r"\bsearch\s+amazon\s+for\s+(.+)$",
        r"\bamazon\s+search\s+(.+)$",
    ]
    for pat in patterns:
        m = re.search(pat, message.strip(), flags=re.IGNORECASE)
        if m:
            q = m.group(1).strip()
            return q or None
    return None


def _extract_email_command(message: str) -> tuple[str, str | None, str | None] | None:
    """
    Supported examples:
    - send email to person@example.com
    - send email to person@example.com about meeting
    - send email to person@example.com about meeting saying let's meet at 5
    """
    m = re.search(
        r"\bsend\s+email\s+to\s+([^\s]+)(?:\s+about\s+(.+?))?(?:\s+saying\s+(.+))?$",
        message.strip(),
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    to_email = (m.group(1) or "").strip()
    subject = (m.group(2) or "").strip() or None
    body = (m.group(3) or "").strip() or None
    return to_email, subject, body


def _extract_timer_seconds(message: str) -> int | None:
    # Supports:
    # - set timer for 10 minutes
    # - set timer for 30 seconds
    # - set a 5 minute timer
    # - timer for 2 minutes
    m = re.search(
        r"\b(?:set\s+)?(?:a\s+)?timer\s+(?:for\s+)?(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b",
        message,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    amount = int(m.group(1))
    if amount <= 0:
        return None
    unit = m.group(2).lower()
    if unit.startswith("sec"):
        return amount
    if unit.startswith("min"):
        return amount * 60
    if unit.startswith("hr") or unit.startswith("hour"):
        return amount * 3600
    return amount


def _is_cancel_timer_request(message: str) -> bool:
    return bool(
        re.search(r"\bcancel\s+(all\s+)?timers?\b", message, flags=re.IGNORECASE)
        or re.search(r"\bstop\s+(all\s+)?timers?\b", message, flags=re.IGNORECASE)
    )


def _extract_reminder_text_and_time(
    message: str,
) -> tuple[str, datetime.datetime | None]:
    """
    Returns (reminder_text, remind_at) where remind_at may be None if the time is missing.
    """
    msg = message.strip()
    # Strip common leading phrases
    prefixes = [
        r"^\s*remind\s+me\s+to\s+",
        r"^\s*remind\s+me\s+that\s+",
        r"^\s*remind\s+me\s+",
        r"^\s*set\s+a\s+reminder\s+to\s+",
        r"^\s*reminder\s*:\s*",
    ]
    candidate = msg
    for pat in prefixes:
        m = re.search(pat, candidate, flags=re.IGNORECASE)
        if m:
            candidate = candidate[m.end():].strip()
            break

    now = timezone.now()

    # Relative time: "in 10 minutes", "in 2 hours", "in 1 day"
    rel = re.search(
        r"\bin\s+(\d+)\s*(minutes?|mins?|hours?|hrs?|days?)\b",
        candidate,
        flags=re.IGNORECASE,
    )
    if rel:
        amount = int(rel.group(1))
        unit = rel.group(2).lower()
        if unit.startswith("min"):
            remind_at = now + datetime.timedelta(minutes=amount)
        elif unit.startswith("hour") or unit.startswith("hrs"):
            remind_at = now + datetime.timedelta(hours=amount)
        else:
            remind_at = now + datetime.timedelta(days=amount)

        text_part = candidate[: rel.start()].strip(" ,.")
        reminder_text = text_part or candidate
        return reminder_text, remind_at

    # Absolute time today/tomorrow: "tomorrow at 7:30 pm", "today at 09:00"
    day_shift = 0
    if re.search(r"\btomorrow\b", candidate, flags=re.IGNORECASE):
        day_shift = 1
    elif re.search(r"\btoday\b", candidate, flags=re.IGNORECASE):
        day_shift = 0

    mtime = re.search(
        r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
        candidate,
        flags=re.IGNORECASE,
    )
    if mtime:
        hour = int(mtime.group(1))
        minute = int(mtime.group(2) or "0")
        ampm = mtime.group(3)
        if ampm:
            ampm = ampm.lower()
            if ampm == "pm" and hour != 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0

        remind_date = (now + datetime.timedelta(days=day_shift)).date()
        remind_at_naive = datetime.datetime.combine(
            remind_date,
            datetime.time(hour=hour, minute=minute),
        )
        remind_at = timezone.make_aware(remind_at_naive, timezone.get_current_timezone())

        # If it's already past and user didn't say "tomorrow", assume tomorrow.
        if day_shift == 0 and remind_at <= now:
            remind_at = remind_at + datetime.timedelta(days=1)

        text_part = candidate[: mtime.start()].strip(" ,.")
        reminder_text = text_part or candidate
        # If the user wrote "tomorrow at ...", drop the trailing day marker.
        reminder_text = re.sub(
            r"(?:\b(today|tomorrow)\b)\s*$",
            "",
            reminder_text,
            flags=re.IGNORECASE,
        ).strip(" ,.")
        return reminder_text, remind_at

    # No time detected
    reminder_text = candidate.strip(" ,.")
    return reminder_text, None


def _handle_reminder_request(message: str, *, conversation: Conversation) -> str:
    reminder_text, remind_at = _extract_reminder_text_and_time(message)
    reminder_text = (reminder_text or "").strip()
    if not reminder_text:
        reminder_text = "your task"

    if not remind_at:
        return (
            "Sure. What date and time should I remind you? "
            "(Example: `remind me to drink water in 10 minutes` or `tomorrow at 7 pm`)"
        )

    Reminder.objects.create(
        conversation=conversation,
        remind_at=remind_at,
        text=reminder_text,
    )
    when = timezone.localtime(remind_at).strftime("%Y-%m-%d %H:%M")
    return f"Okay! I’ll remind you to: {reminder_text} (at {when})."


@csrf_exempt
def chat_api(request):
    """
    Accepts either:
    - GET: ?message=...&conv_id=...
    - POST JSON: { "message": "...", "conv_id": ... }
    """
    if request.method == "POST":
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        user_message = payload.get("message")
        conv_id = payload.get("conv_id")
    else:
        user_message = request.GET.get("message")
        conv_id = request.GET.get("conv_id")

    if not user_message or not str(user_message).strip():
        return JsonResponse({"error": "message is required"}, status=400)

    user_message = _truncate(str(user_message), _max_int("MAX_MESSAGE_CHARS", 2000))

    if conv_id:
        try:
            conversation = Conversation.objects.get(id=conv_id)
        except Conversation.DoesNotExist:
            conversation = Conversation.objects.create()
    else:
        conversation = Conversation.objects.create()

    lower_msg = str(user_message).lower()
    profile = _get_user_profile()
    _extract_profile_updates(user_message, profile)
    detected_mood, mood_intensity = _detect_mood(user_message)
    if detected_mood != "neutral":
        MoodLog.objects.create(
            mood=detected_mood,
            intensity=mood_intensity,
            message=user_message,
            conversation=conversation,
        )

    mood_meta = {"detected_mood": detected_mood, "mood_intensity": mood_intensity}

    # Handle interrupt/stop commands
    if re.search(r"\b(stop|quit|exit|cancel all|interrupt|shut down|abort|halt|enough|stop it|shut up|stop listening|stop voice)\b", lower_msg):
        return JsonResponse({
            "response": "Stopped! 🛑",
            "conv_id": conversation.id,
            "action": {"type": "stop_all"},
            **mood_meta
        })

    auto_mode_response = _handle_auto_mode_command(lower_msg, profile)
    if auto_mode_response:
        Memory.objects.create(conversation=conversation, message=user_message, response=auto_mode_response)
        if conversation.title == "New Chat":
            conversation.title = user_message[:60] or "New Chat"
            conversation.save(update_fields=["title"])
        return JsonResponse({"response": auto_mode_response, "conv_id": conversation.id, **mood_meta})

    goal_response = _handle_goal_commands(user_message)
    if goal_response:
        Memory.objects.create(conversation=conversation, message=user_message, response=goal_response)
        if conversation.title == "New Chat":
            conversation.title = user_message[:60] or "New Chat"
            conversation.save(update_fields=["title"])
        return JsonResponse({"response": goal_response, "conv_id": conversation.id, **mood_meta})

    # Handle habit commands
    habit_response = _handle_habit_commands(user_message)
    if habit_response:
        Memory.objects.create(conversation=conversation, message=user_message, response=habit_response)
        if conversation.title == "New Chat":
            conversation.title = user_message[:60] or "New Chat"
            conversation.save(update_fields=["title"])
        return JsonResponse({"response": habit_response, "conv_id": conversation.id, **mood_meta})

    memory_response = _handle_memory_command(lower_msg, conversation)
    if memory_response:
        Memory.objects.create(conversation=conversation, message=user_message, response=memory_response)
        if conversation.title == "New Chat":
            conversation.title = user_message[:60] or "New Chat"
            conversation.save(update_fields=["title"])
        return JsonResponse({"response": memory_response, "conv_id": conversation.id, **mood_meta})

    # Specialized actions (weather/reminders) so the assistant can do things.
    if _is_weather_request(lower_msg):
        reply = _handle_weather_request(lower_msg)
        Memory.objects.create(conversation=conversation, message=user_message, response=reply)
        if conversation.title == "New Chat":
            conversation.title = user_message[:60] or "New Chat"
            conversation.save(update_fields=["title"])
        return JsonResponse({"response": reply, "conv_id": conversation.id, **mood_meta})

    if _is_reminder_request(lower_msg):
        reply = _handle_reminder_request(lower_msg, conversation=conversation)
        Memory.objects.create(conversation=conversation, message=user_message, response=reply)
        if conversation.title == "New Chat":
            conversation.title = user_message[:60] or "New Chat"
            conversation.save(update_fields=["title"])
        return JsonResponse({"response": reply, "conv_id": conversation.id, **mood_meta})

    if profile.auto_agent_mode:
        inferred = _infer_auto_action(lower_msg)
        if inferred:
            reply = inferred.get("response") or "Done."
            Memory.objects.create(conversation=conversation, message=user_message, response=reply)
            if conversation.title == "New Chat":
                conversation.title = user_message[:60] or "New Chat"
                conversation.save(update_fields=["title"])
            return JsonResponse(
                {
                    "response": reply,
                    "conv_id": conversation.id,
                    "action": inferred.get("action"),
                    **mood_meta,
                }
            )

    open_target = _extract_open_target(lower_msg)
    if open_target:
        open_action = _action_for_open_target(open_target)
        if open_action:
            reply = open_action["response"]
            Memory.objects.create(conversation=conversation, message=user_message, response=reply)
            if conversation.title == "New Chat":
                conversation.title = user_message[:60] or "New Chat"
                conversation.save(update_fields=["title"])
            return JsonResponse(
                {
                    "response": reply,
                    "conv_id": conversation.id,
                    "action": open_action.get("action"),
                    **mood_meta,
                }
            )
    
    # Universal website opener - open ANY website by name
    website_match = re.search(
        r"\b(?:open|launch|go to|visit|browse)\s+(?:the\s+)?(?:website\s+)?(?:called\s+)?([a-z0-9]+(?:\.[a-z]+)?)\b",
        lower_msg,
        flags=re.IGNORECASE
    )
    if website_match:
        website_name = website_match.group(1).strip().lower()
        url = _resolve_open_url(website_name)
        
        if url:
            site_display = website_name.replace('.', ' ').title()
            reply = f"Opening {site_display}..."
            Memory.objects.create(conversation=conversation, message=user_message, response=reply)
            if conversation.title == "New Chat":
                conversation.title = f"Opening {site_display}"
                conversation.save(update_fields=["title"])
            return JsonResponse(
                {
                    "response": reply,
                    "conv_id": conversation.id,
                    "action": {"type": "open_url", "url": url},
                    **mood_meta,
                }
            )
        else:
            # Try to construct URL
            if '.' not in website_name:
                url = f"https://www.{website_name}.com"
            else:
                url = f"https://{website_name}"
            
            reply = f"Trying to open {website_name}..."
            Memory.objects.create(conversation=conversation, message=user_message, response=reply)
            return JsonResponse(
                {
                    "response": reply,
                    "conv_id": conversation.id,
                    "action": {"type": "open_url", "url": url},
                    **mood_meta,
                }
            )

    google_query = _extract_google_search_query(lower_msg)
    if google_query:
        url = f"https://www.google.com/search?q={quote_plus(google_query)}"
        reply = f"Searching Google for {google_query}."
        Memory.objects.create(conversation=conversation, message=user_message, response=reply)
        if conversation.title == "New Chat":
            conversation.title = f"Search: {google_query[:40]}"
            conversation.save(update_fields=["title"])
        return JsonResponse(
            {
                "response": reply,
                "conv_id": conversation.id,
                "action": {"type": "open_url", "url": url},
                **mood_meta,
            }
        )
    
    # Universal search - detect questions and auto-search
    general_search = _detect_general_search(lower_msg)
    if general_search and len(general_search.split()) <= 15:  # Only for short questions
        url = f"https://www.google.com/search?q={quote_plus(general_search)}"
        reply = f"Searching Google for: {general_search}?"
        Memory.objects.create(conversation=conversation, message=user_message, response=reply)
        if conversation.title == "New Chat":
            conversation.title = f"Q: {general_search[:40]}?"
            conversation.save(update_fields=["title"])
        return JsonResponse(
            {
                "response": reply,
                "conv_id": conversation.id,
                "action": {"type": "open_url", "url": url},
                **mood_meta,
            }
        )

    youtube_query = _extract_youtube_query(lower_msg)
    if youtube_query:
        url = f"https://www.youtube.com/results?search_query={quote_plus(youtube_query)}"
        reply = f"Playing {youtube_query} on YouTube 🎵"
        Memory.objects.create(conversation=conversation, message=user_message, response=reply)
        if conversation.title == "New Chat":
            conversation.title = f"🎵 Playing: {youtube_query[:40]}"
            conversation.save(update_fields=["title"])
        return JsonResponse(
            {
                "response": reply,
                "conv_id": conversation.id,
                "action": {"type": "open_url", "url": url},
                **mood_meta,
            }
        )
    
    # Detect song/music requests and auto-search on YouTube
    song_request = _detect_song_request(lower_msg)
    if song_request:
        search_query = song_request if song_request != "music" else "latest hit songs"
        url = f"https://www.youtube.com/results?search_query={quote_plus(search_query)}"
        reply = f"Playing {search_query} on YouTube 🎵"
        Memory.objects.create(conversation=conversation, message=user_message, response=reply)
        if conversation.title == "New Chat":
            conversation.title = f"🎵 Music: {search_query[:40]}"
            conversation.save(update_fields=["title"])
        return JsonResponse(
            {
                "response": reply,
                "conv_id": conversation.id,
                "action": {"type": "open_url", "url": url},
                **mood_meta,
            }
        )

    maps_query = _extract_maps_query(lower_msg)
    if maps_query:
        place, is_nav = maps_query
        if place:
            if is_nav:
                url = f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(place)}"
                reply = f"Starting navigation to {place}."
            else:
                url = f"https://www.google.com/maps/search/{quote_plus(place)}"
                reply = f"Opening maps for {place}."
            Memory.objects.create(conversation=conversation, message=user_message, response=reply)
            if conversation.title == "New Chat":
                conversation.title = user_message[:60] or "New Chat"
                conversation.save(update_fields=["title"])
            return JsonResponse(
                {
                    "response": reply,
                    "conv_id": conversation.id,
                    "action": {"type": "open_url", "url": url},
                    **mood_meta,
                }
            )

    amazon_query = _extract_amazon_query(lower_msg)
    if amazon_query:
        url = f"https://www.amazon.in/s?k={quote_plus(amazon_query)}"
        reply = f"Searching Amazon for {amazon_query}."
        Memory.objects.create(conversation=conversation, message=user_message, response=reply)
        if conversation.title == "New Chat":
            conversation.title = user_message[:60] or "New Chat"
            conversation.save(update_fields=["title"])
        return JsonResponse(
            {
                "response": reply,
                "conv_id": conversation.id,
                "action": {"type": "open_url", "url": url},
                **mood_meta,
            }
        )

    email_cmd = _extract_email_command(lower_msg)
    if email_cmd:
        to_email, subject, body = email_cmd
        mailto = f"mailto:{to_email}"
        params = []
        if subject:
            params.append(f"subject={quote_plus(subject)}")
        if body:
            params.append(f"body={quote_plus(body)}")
        if params:
            mailto += "?" + "&".join(params)
        reply = f"Opening email composer for {to_email}."
        Memory.objects.create(conversation=conversation, message=user_message, response=reply)
        if conversation.title == "New Chat":
            conversation.title = user_message[:60] or "New Chat"
            conversation.save(update_fields=["title"])
        return JsonResponse(
            {
                "response": reply,
                "conv_id": conversation.id,
                "action": {"type": "open_url", "url": mailto},
                **mood_meta,
            }
        )

    if _is_cancel_timer_request(lower_msg):
        reply = "Okay, canceling all active timers."
        Memory.objects.create(conversation=conversation, message=user_message, response=reply)
        if conversation.title == "New Chat":
            conversation.title = user_message[:60] or "New Chat"
            conversation.save(update_fields=["title"])
        return JsonResponse(
            {
                "response": reply,
                "conv_id": conversation.id,
                "action": {"type": "cancel_timers"},
                **mood_meta,
            }
        )

    timer_seconds = _extract_timer_seconds(lower_msg)
    if timer_seconds:
        if timer_seconds % 60 == 0:
            minutes = timer_seconds // 60
            timer_label = f"{minutes}-minute timer"
            reply = f"Timer set for {minutes} minute{'s' if minutes != 1 else ''}."
        else:
            timer_label = f"{timer_seconds}-second timer"
            reply = f"Timer set for {timer_seconds} second{'s' if timer_seconds != 1 else ''}."
        Memory.objects.create(conversation=conversation, message=user_message, response=reply)
        if conversation.title == "New Chat":
            conversation.title = user_message[:60] or "New Chat"
            conversation.save(update_fields=["title"])
        return JsonResponse(
            {
                "response": reply,
                "conv_id": conversation.id,
                "action": {"type": "set_timer", "seconds": timer_seconds, "label": timer_label},
                **mood_meta,
            }
        )

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        return JsonResponse({"error": "OPENAI_API_KEY is not set", **mood_meta}, status=500)

    memory_updates = _extract_personal_memories(user_message, conversation)
    personal_memory_lines = _get_personal_memory_lines(limit=20)

    # Limit history to keep latency and token usage reasonable.
    max_history = _max_int("MAX_HISTORY_MESSAGES", 20)
    history_rows = list(
        Memory.objects.filter(conversation=conversation)
        .order_by("created_at")
        .values("message", "response")
    )[-max_history:]
    
    # Get cross-conversation context (recent interactions from other conversations)
    recent_other_convos = list(
        Memory.objects.exclude(conversation=conversation)
        .order_by("-created_at")
        .values("message", "response")[:6]
    )
    
    # Build enhanced AI context
    messages = [{"role": "system", "content": _system_prompt()}]
    
    # User profile context
    messages.append({"role": "system", "content": _build_profile_context(profile)})
    
    # Goal context
    messages.append({"role": "system", "content": _goal_context_text()})
    
    # Emotional context
    messages.append({"role": "system", "content": _emotional_recent_context(conversation)})
    
    # Mood guidance
    messages.append({"role": "system", "content": _mood_response_guidance(detected_mood, mood_intensity)})
    
    # Personal memories
    if personal_memory_lines:
        messages.append(
            {
                "role": "system",
                "content": "USER MEMORY (things you know about the user):\n- " + "\n- ".join(personal_memory_lines),
            }
        )
    
    # Cross-conversation context
    if recent_other_convos:
        cross_context = "RECENT INTERACTIONS FROM OTHER CONVERSATIONS:\n"
        for i, row in enumerate(recent_other_convos[:4]):
            cross_context += f"- User: {row['message'][:80]}\n  You: {row['response'][:80]}\n"
        messages.append({
            "role": "system",
            "content": cross_context
        })
    
    # Context awareness
    messages.append(
        {
            "role": "system",
            "content": _build_context_awareness_message(conversation, history_rows, user_message),
        }
    )
    
    # Smart memory injection - recall relevant past interactions
    if history_rows:
        relevant_context = _extract_relevant_context(user_message, history_rows)
        if relevant_context:
            messages.append({
                "role": "system",
                "content": f"RELEVANT PAST CONTEXT:\n{relevant_context}"
            })
    
    # Add conversation history
    for row in history_rows:
        messages.append({"role": "user", "content": row["message"]})
        messages.append({"role": "assistant", "content": row["response"]})
    
    # Current message
    messages.append({"role": "user", "content": user_message})
    
    # Adaptive temperature based on context
    temp = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
    if detected_mood == "crisis":
        temp = min(temp, 0.4)
    elif detected_mood in {"sad", "lonely", "worried", "stressed"}:
        temp = min(temp, 0.5)
    elif "creative" in user_message.lower() or "brainstorm" in user_message.lower():
        temp = max(temp, 0.8)
    
    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "messages": messages,
        "temperature": temp,
        "max_tokens": 1000,
        "presence_penalty": 0.3,
        "frequency_penalty": 0.3,
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=_max_int("OPENAI_TIMEOUT_SECONDS", 45),
        )
        data = response.json()
        reply = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if not reply:
            reply = data.get("error", {}).get("message") or "AI returned an empty response."
    except requests.exceptions.Timeout:
        reply = "The AI took too long to respond. Please try again with a simpler question."
    except requests.exceptions.RequestException:
        reply = "Network error connecting to AI. Check your internet connection."
    except Exception:
        reply = "Error connecting to AI"

    # Proactive suggestions
    suggestion = _proactive_suggestion(detected_mood, profile, user_message)
    if suggestion and len(reply) < 300:
        reply = f"{reply}\n\n{suggestion}"

    # Save to memory
    Memory.objects.create(conversation=conversation, message=user_message, response=reply)
    _update_conversation_context(conversation, history_rows, user_message, reply)

    # Auto-title conversation
    if conversation.title == "New Chat":
        preview = user_message[:60]
        if len(user_message) > 60:
            preview += "..."
        conversation.title = preview or "New Chat"
        conversation.save(update_fields=["title"])

    return JsonResponse({"response": reply, "conv_id": conversation.id, **mood_meta})


def _extract_relevant_context(user_message: str, history_rows: list) -> str:
    """Extract most relevant past interactions based on keyword matching."""
    user_words = set(user_message.lower().split())
    scored_rows = []
    
    for row in history_rows[-10:]:
        msg_words = set((row.get('message', '') + ' ' + row.get('response', '')).lower().split())
        overlap = len(user_words & msg_words)
        if overlap > 0:
            scored_rows.append((overlap, row))
    
    if not scored_rows:
        return ""
    
    scored_rows.sort(reverse=True, key=lambda x: x[0])
    top_matches = scored_rows[:2]
    
    context = ""
    for score, row in top_matches:
        context += f"Earlier you discussed: {row['message'][:100]}\n"
    
    return context.strip()


def ai_status_api(request):
    """API endpoint to check AI engine status and stats."""
    from django.db.models import Count
    
    total_conversations = Conversation.objects.count()
    total_messages = Memory.objects.count()
    active_goal = _get_active_goal()
    active_habits = HabitTracker.objects.filter(is_active=True).count()
    
    return JsonResponse({
        'status': 'online',
        'model': os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),
        'stats': {
            'total_conversations': total_conversations,
            'total_messages': total_messages,
            'active_goal': active_goal.title if active_goal else None,
            'active_habits': active_habits,
        },
        'features': {
            'voice_commands': True,
            'goal_tracking': True,
            'habit_tracking': True,
            'emotion_detection': True,
            'cross_conversation_memory': True,
            'context_awareness': True,
            'proactive_suggestions': True,
        }
    })


def load_chat(request):
    conv_id = request.GET.get('conv_id')
    if not conv_id:
        return JsonResponse({"chats": []})

    chats = (
        Memory.objects.filter(conversation_id=conv_id)
        .order_by("created_at")
        .values("message", "response")
    )

    data = []
    for chat in chats:
        data.append({
            "message": chat["message"],
            "response": chat["response"],
        })

    return JsonResponse({"chats": data})


def conversations_api(request):
    last_memory = (
        Memory.objects.filter(conversation_id=OuterRef("pk"))
        .order_by("-created_at")
    )

    qs = (
        Conversation.objects.all()
        .annotate(
            last_user_message=Subquery(last_memory.values("message")[:1]),
            last_ai_message=Subquery(last_memory.values("response")[:1]),
            last_at=Subquery(last_memory.values("created_at")[:1]),
        )
        .order_by("-is_pinned", "-last_at", "-created_at")
        .values("id", "title", "is_pinned", "last_user_message", "last_ai_message", "last_at")
    )

    conversations = []
    for row in list(qs):
        preview = (row.get("last_user_message") or "").strip()
        if not preview:
            preview = (row.get("last_ai_message") or "").strip()
        preview = preview[:120] + ("..." if len(preview) > 120 else "")
        last_at = row.get("last_at")
        conversations.append(
            {
                "id": row["id"],
                "title": row.get("title") or "Conversation",
                "is_pinned": bool(row.get("is_pinned")),
                "preview": preview,
                "last_at": last_at.isoformat() if last_at else None,
            }
        )

    return JsonResponse({"conversations": conversations})


@csrf_exempt
def delete_conversation_api(request, conv_id: int):
    if request.method not in ("POST", "DELETE"):
        return JsonResponse({"error": "method not allowed"}, status=405)

    try:
        conversation = Conversation.objects.get(id=conv_id)
    except Conversation.DoesNotExist:
        return JsonResponse({"ok": True})

    conversation.delete()
    return JsonResponse({"ok": True})


@csrf_exempt
def toggle_pin_conversation_api(request, conv_id: int):
    if request.method not in ("POST", "PATCH"):
        return JsonResponse({"error": "method not allowed"}, status=405)

    try:
        conversation = Conversation.objects.get(id=conv_id)
    except Conversation.DoesNotExist:
        return JsonResponse({"error": "conversation not found"}, status=404)

    conversation.is_pinned = not conversation.is_pinned
    conversation.save(update_fields=["is_pinned"])
    return JsonResponse({"ok": True, "is_pinned": conversation.is_pinned})


@csrf_exempt
def rename_conversation_api(request, conv_id: int):
    if request.method not in ("POST", "PATCH"):
        return JsonResponse({"error": "method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}

    new_title = (payload.get("title") or "").strip()
    if not new_title:
        return JsonResponse({"error": "title is required"}, status=400)
    if len(new_title) > 200:
        new_title = new_title[:200]

    try:
        conversation = Conversation.objects.get(id=conv_id)
    except Conversation.DoesNotExist:
        return JsonResponse({"error": "conversation not found"}, status=404)

    conversation.title = new_title
    conversation.save(update_fields=["title"])
    return JsonResponse({"ok": True, "title": conversation.title})


def reminders_api(request):
    now = timezone.now()
    conv_id = request.GET.get("conv_id")

    qs = Reminder.objects.filter(remind_at__lte=now, delivered_at__isnull=True).order_by("remind_at")
    if conv_id:
        qs = qs.filter(conversation_id=conv_id)

    reminders = list(qs[:50])
    delivered_at = timezone.now()
    for r in reminders:
        r.delivered_at = delivered_at
        r.save(update_fields=["delivered_at"])

    return JsonResponse(
        {
            "reminders": [
                {
                    "id": r.id,
                    "text": r.text,
                    "conv_id": r.conversation_id,
                    "remind_at": r.remind_at.isoformat(),
                }
                for r in reminders
            ]
        }
    )


@csrf_exempt
def chat_stream_api(request):
    """
    Real-time streaming AI endpoint. Uses Server-Sent Events (SSE) to stream 
    tokens as they are generated, enabling instant speech and typewriter UI.
    """
    if request.method == "POST":
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        user_message = payload.get("message")
        conv_id = payload.get("conv_id")
    else:
        user_message = request.GET.get("message")
        conv_id = request.GET.get("conv_id")

    if not user_message or not str(user_message).strip():
        def error_gen():
            yield "data: " + json.dumps({"error": "message is required"}) + "\n\n"
        return StreamingHttpResponse(error_gen(), content_type='text/event-stream')

    user_message = _truncate(str(user_message), _max_int("MAX_MESSAGE_CHARS", 2000))
    lower_msg = user_message.lower()

    if conv_id:
        try:
            conversation = Conversation.objects.get(id=conv_id)
        except Conversation.DoesNotExist:
            conversation = Conversation.objects.create()
    else:
        conversation = Conversation.objects.create()

    profile = _get_user_profile()
    detected_mood, mood_intensity = _detect_mood(user_message)
    mood_meta = {"detected_mood": detected_mood, "mood_intensity": mood_intensity}

    # Handle specialized commands that shouldn't be streamed
    auto_mode_response = _handle_auto_mode_command(lower_msg, profile)
    if auto_mode_response:
        def cmd_gen():
            resp_text = auto_mode_response.get("response") if isinstance(auto_mode_response, dict) else auto_mode_response
            action = auto_mode_response.get("action") if isinstance(auto_mode_response, dict) else None
            yield "data: " + json.dumps({"response": resp_text, "conv_id": conversation.id, "action": action, **mood_meta}) + "\n\n"
        Memory.objects.create(conversation=conversation, message=user_message, response=resp_text)
        return StreamingHttpResponse(cmd_gen(), content_type='text/event-stream')

    # --- NEW: Handle auto actions (open sites, timers, etc.) ---
    inferred_action = _infer_auto_action(lower_msg)
    if inferred_action:
        def action_gen():
            yield "data: " + json.dumps({
                "response": inferred_action.get("response"), 
                "conv_id": conversation.id, 
                "action": inferred_action.get("action"), 
                **mood_meta
            }) + "\n\n"
        Memory.objects.create(conversation=conversation, message=user_message, response=inferred_action.get("response"))
        return StreamingHttpResponse(action_gen(), content_type='text/event-stream')
    # ----------------------------------------------------------

    goal_response = _handle_goal_commands(user_message)
    if goal_response:
        def goal_gen():
            yield "data: " + json.dumps({"response": goal_response, "conv_id": conversation.id, **mood_meta}) + "\n\n"
        Memory.objects.create(conversation=conversation, message=user_message, response=goal_response)
        return StreamingHttpResponse(goal_gen(), content_type='text/event-stream')

    # Handle Student Commands
    student_response = _handle_student_command(user_message)
    if student_response:
        def student_gen():
            yield "data: " + json.dumps({
                "response": student_response.get("response"), 
                "conv_id": conversation.id, 
                "action": student_response.get("action"), 
                **mood_meta
            }) + "\n\n"
        Memory.objects.create(conversation=conversation, message=user_message, response=student_response.get("response"))
        return StreamingHttpResponse(student_gen(), content_type='text/event-stream')

    # Handle Media Commands
    media_response = _handle_media_command(user_message)
    if media_response:
        def media_gen():
            yield "data: " + json.dumps({
                "response": media_response.get("response"), 
                "conv_id": conversation.id, 
                "action": media_response.get("action"), 
                **mood_meta
            }) + "\n\n"
        Memory.objects.create(conversation=conversation, message=user_message, response=media_response.get("response"))
        return StreamingHttpResponse(media_gen(), content_type='text/event-stream')

    # Handle Task Commands
    task_response = _handle_task_command(user_message)
    if task_response:
        def task_gen():
            yield "data: " + json.dumps({
                "response": task_response.get("response"), 
                "conv_id": conversation.id, 
                "action": task_response.get("action"), 
                **mood_meta
            }) + "\n\n"
        Memory.objects.create(conversation=conversation, message=user_message, response=task_response.get("response"))
        return StreamingHttpResponse(task_gen(), content_type='text/event-stream')

    # AI Generation with Streaming
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        def err_gen():
            yield "data: " + json.dumps({"error": "OPENAI_API_KEY is not set"}) + "\n\n"
        return StreamingHttpResponse(err_gen(), content_type='text/event-stream')

    personal_memory_lines = _get_personal_memory_lines(limit=20)
    max_history = _max_int("MAX_HISTORY_MESSAGES", 20)
    history_rows = list(
        Memory.objects.filter(conversation=conversation)
        .order_by("created_at")
        .values("message", "response")
    )[-max_history:]

    messages = [{"role": "system", "content": _system_prompt()}]
    messages.append({"role": "system", "content": _build_profile_context(profile)})
    messages.append({"role": "system", "content": _goal_context_text()})
    messages.append({"role": "system", "content": _emotional_recent_context(conversation)})
    messages.append({"role": "system", "content": _mood_response_guidance(detected_mood, mood_intensity)})
    if personal_memory_lines:
        messages.append({"role": "system", "content": "Known user memory:\n- " + "\n- ".join(personal_memory_lines)})
    
    for row in history_rows:
        messages.append({"role": "user", "content": row["message"]})
        messages.append({"role": "assistant", "content": row["response"]})
    messages.append({"role": "user", "content": user_message})

    temp = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
    if detected_mood == "crisis":
        temp = min(temp, 0.4)
    elif detected_mood in {"sad", "lonely", "worried", "stressed"}:
        temp = min(temp, 0.5)

    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "messages": messages,
        "temperature": temp,
        "stream": True
    }

    def event_stream():
        full_reply = ""
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                stream=True,
                timeout=_max_int("OPENAI_TIMEOUT_SECONDS", 45),
            )
            
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith('data: '):
                        try:
                            chunk = json.loads(decoded_line[6:])
                            if chunk.get('choices') and len(chunk['choices']) > 0:
                                delta = chunk['choices'][0].get('delta', {})
                                content = delta.get('content')
                                if content:
                                    full_reply += content
                                    # Send token to frontend
                                    yield f"data: {json.dumps({'token': content})}\n\n"
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        # Finalize response
        suggestion = _proactive_suggestion(detected_mood, profile, user_message)
        if suggestion:
            full_reply += f"\n\n{suggestion}"
            yield f"data: {json.dumps({'token': '\n\n' + suggestion})}\n\n"

        # Save to memory and update context
        Memory.objects.create(conversation=conversation, message=user_message, response=full_reply)
        _update_conversation_context(conversation, history_rows, user_message, full_reply)

        # Set title if new
        if conversation.title == "New Chat":
            preview = user_message[:60]
            conversation.title = preview or "New Chat"
            conversation.save(update_fields=["title"])

        # Send completion metadata
        yield f"data: {json.dumps({'done': True, 'response': full_reply, 'conv_id': conversation.id, **mood_meta})}\n\n"

    return StreamingHttpResponse(event_stream(), content_type='text/event-stream')
from django.db import models
from django.utils import timezone

class Conversation(models.Model):
    title = models.CharField(max_length=200, default="New Chat")
    is_pinned = models.BooleanField(default=False)
    running_summary = models.TextField(default="", blank=True)
    current_topic = models.CharField(max_length=200, default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Memory(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    message = models.TextField()
    response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class Reminder(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reminders",
    )
    remind_at = models.DateTimeField()
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    # When the reminder has been sent to the UI for delivery.
    delivered_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_due(self) -> bool:
        return self.remind_at <= timezone.now() and self.delivered_at is None


class PersonalMemory(models.Model):
    key = models.CharField(max_length=100)
    value = models.TextField()
    source_conversation = models.ForeignKey(
        Conversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="personal_memories",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class UserProfile(models.Model):
    # Single-profile setup for this local assistant instance.
    display_name = models.CharField(max_length=120, default="", blank=True)
    habit_goals = models.TextField(default="", blank=True)
    preferences = models.TextField(default="", blank=True)
    auto_agent_mode = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)


class MoodLog(models.Model):
    mood = models.CharField(max_length=40)
    intensity = models.CharField(max_length=20, default="medium")
    message = models.TextField()
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mood_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True)


class UserGoal(models.Model):
    title = models.CharField(max_length=240)
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=30, default="active")  # active/completed/paused
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class GoalStep(models.Model):
    goal = models.ForeignKey(UserGoal, on_delete=models.CASCADE, related_name="steps")
    text = models.TextField()
    is_done = models.BooleanField(default=False)
    step_order = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)


class HabitTracker(models.Model):
    """A habit to track daily/recurring activities."""
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('custom', 'Custom'),
    ]
    
    name = models.CharField(max_length=120)
    description = models.TextField(default="", blank=True)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='daily')
    target_days = models.CharField(
        max_length=50,
        default="1,2,3,4,5,6,0",  # All days (0=Sunday, 6=Saturday)
        help_text="Comma-separated day numbers (0=Sunday, 6=Saturday)"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.frequency})"
    
    @property
    def current_streak(self) -> int:
        """Calculate current streak of consecutive completions."""
        logs = self.logs.filter(completed=True).order_by('-date')
        if not logs:
            return 0
        
        streak = 0
        expected_date = timezone.now().date()
        
        for log in logs:
            if log.date == expected_date:
                streak += 1
                expected_date -= timezone.timedelta(days=1)
            elif log.date < expected_date:
                break
        
        return streak
    
    @property
    def best_streak(self) -> int:
        """Calculate best streak ever achieved."""
        logs = self.logs.filter(completed=True).order_by('date')
        if not logs:
            return 0
        
        best = 0
        current = 1
        
        for i in range(1, len(logs)):
            if (logs[i].date - logs[i-1].date).days == 1:
                current += 1
            else:
                current = 1
            best = max(best, current)
        
        return max(best, current)
    
    @property
    def completion_rate(self) -> float:
        """Calculate completion rate over last 30 days."""
        thirty_days_ago = timezone.now().date() - timezone.timedelta(days=30)
        total_days = (timezone.now().date() - thirty_days_ago).days + 1
        completed = self.logs.filter(completed=True, date__gte=thirty_days_ago).count()
        return round((completed / total_days) * 100, 1) if total_days > 0 else 0


class HabitLog(models.Model):
    """Daily log for tracking habit completion."""
    habit = models.ForeignKey(HabitTracker, on_delete=models.CASCADE, related_name="logs")
    date = models.DateField()
    completed = models.BooleanField(default=False)
    notes = models.TextField(default="", blank=True)
    mood_before = models.CharField(max_length=40, default="", blank=True)
    mood_after = models.CharField(max_length=40, default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['habit', 'date']
        ordering = ['-date']
    
    def __str__(self):
        status = "✓" if self.completed else "✗"
        return f"{self.habit.name} - {self.date} ({status})"


class Task(models.Model):
    """A task to be completed."""
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    title = models.CharField(max_length=200)
    description = models.TextField(default="", blank=True)
    is_completed = models.BooleanField(default=False)
    due_date = models.DateTimeField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class Subject(models.Model):
    """A course or subject the student is studying."""
    name = models.CharField(max_length=100)
    teacher = models.CharField(max_length=100, blank=True, default="")
    color = models.CharField(max_length=20, default="#3b82f6")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Assignment(models.Model):
    """Homework or assignment for a subject."""
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="assignments")
    title = models.CharField(max_length=200)
    description = models.TextField(default="", blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.subject.name})"


class Exam(models.Model):
    """Upcoming exam or test."""
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="exams")
    title = models.CharField(max_length=200)
    exam_date = models.DateTimeField()
    topics = models.TextField(default="", blank=True, help_text="Comma separated topics")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.exam_date.strftime('%b %d, %I:%M %p')}"


class MediaPreference(models.Model):
    """User's preferred media platforms."""
    music_platform = models.CharField(max_length=50, default="youtube") # youtube, spotify
    video_platform = models.CharField(max_length=50, default="youtube") # youtube, netflix
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
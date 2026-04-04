from django.contrib import admin
from .models import Conversation, Memory, Reminder, PersonalMemory, UserProfile, MoodLog, UserGoal, GoalStep


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "current_topic", "created_at")
    ordering = ("-created_at",)


@admin.register(Memory)
class MemoryAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "created_at")
    ordering = ("created_at",)


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "remind_at", "delivered_at")
    ordering = ("remind_at",)


@admin.register(PersonalMemory)
class PersonalMemoryAdmin(admin.ModelAdmin):
    list_display = ("id", "key", "value", "source_conversation", "updated_at")
    ordering = ("-updated_at",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "display_name", "auto_agent_mode", "updated_at")
    ordering = ("-updated_at",)


@admin.register(MoodLog)
class MoodLogAdmin(admin.ModelAdmin):
    list_display = ("id", "mood", "intensity", "conversation", "created_at")
    ordering = ("-created_at",)


@admin.register(UserGoal)
class UserGoalAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "is_active", "updated_at")
    ordering = ("-updated_at",)


@admin.register(GoalStep)
class GoalStepAdmin(admin.ModelAdmin):
    list_display = ("id", "goal", "step_order", "is_done", "created_at")
    ordering = ("goal", "step_order")
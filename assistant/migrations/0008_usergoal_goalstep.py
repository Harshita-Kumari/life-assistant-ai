from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("assistant", "0007_userprofile_auto_agent_mode"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserGoal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=240)),
                ("is_active", models.BooleanField(default=True)),
                ("status", models.CharField(default="active", max_length=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="GoalStep",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.TextField()),
                ("is_done", models.BooleanField(default=False)),
                ("step_order", models.IntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "goal",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="steps", to="assistant.usergoal"),
                ),
            ],
        ),
    ]


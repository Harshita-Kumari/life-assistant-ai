from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("assistant", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Reminder",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("remind_at", models.DateTimeField()),
                ("text", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                (
                    "conversation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reminders",
                        to="assistant.conversation",
                    ),
                ),
            ],
        ),
    ]


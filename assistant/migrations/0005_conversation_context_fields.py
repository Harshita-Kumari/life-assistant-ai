from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("assistant", "0004_personalmemory"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="current_topic",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="conversation",
            name="running_summary",
            field=models.TextField(blank=True, default=""),
        ),
    ]


from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("assistant", "0006_userprofile_moodlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="auto_agent_mode",
            field=models.BooleanField(default=True),
        ),
    ]


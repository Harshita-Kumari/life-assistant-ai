from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("assistant", "0002_reminder"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="is_pinned",
            field=models.BooleanField(default=False),
        ),
    ]


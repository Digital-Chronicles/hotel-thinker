# Generated for public guest API login/profile linking.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("bookings", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="guest",
            name="user",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional login account linked to this guest profile.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="guest_profiles",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="guest",
            index=models.Index(fields=["user"], name="bookings_gu_user_id_idx"),
        ),
    ]

from django.apps import apps
from django.conf import settings


DEFAULT_ALLOWED_APPS = [
    "rooms",
    "bookings",
    "restaurant",
    "bar",
    "services",
    "store",
    "finance",
]


BLOCKED_MODELS = {
    "auth.permission",
    "contenttypes.contenttype",
    "sessions.session",
    "admin.logentry",
}


def get_allowed_apps():
    return getattr(settings, "BULK_ALLOWED_APPS", DEFAULT_ALLOWED_APPS)


def is_model_allowed(model):
    meta = model._meta
    label = f"{meta.app_label}.{meta.model_name}"

    if label in BLOCKED_MODELS:
        return False

    if meta.app_label not in get_allowed_apps():
        return False

    if meta.proxy or not meta.managed:
        return False

    return True


def get_model_choices():
    choices = []

    for model in apps.get_models():
        if not is_model_allowed(model):
            continue

        meta = model._meta
        label = f"{meta.app_label}.{meta.model_name}"
        verbose = f"{meta.app_label.title()} — {meta.verbose_name.title()}"
        choices.append((label, verbose))

    return sorted(choices, key=lambda item: item[1])


def get_model_from_label(model_label):
    if not model_label or "." not in model_label:
        raise ValueError("Choose a valid model.")

    app_label, model_name = model_label.split(".", 1)

    if app_label not in get_allowed_apps():
        raise ValueError("This model is not enabled for bulk operations.")

    model = apps.get_model(app_label, model_name)

    if model is None:
        raise ValueError("Model not found.")

    if not is_model_allowed(model):
        raise ValueError("This model is not safe for bulk operations.")

    return model
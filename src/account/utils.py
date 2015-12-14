from django.contrib.auth.models import User
from django.contrib.auth import authenticate as django_authenticate
import hashlib
from inventory.models import DataHubLegacyUser
from core.db.manager import DataHubManager
from inventory.models import App
from social.backends.utils import load_backends
from operator import itemgetter
from django.conf import settings


def provider_details(backend=None):
    # For templates. Intersect with settings.AUTHENTICATION_BACKENDS to limit
    # to enabled social backends.
    #
    # `backend` is the backend name Python Social Auth understands.
    # `name` is the display name to be shown in templates.
    # `icon` is the id of the Font Awesome icon matching the backend.
    # `priority` is the sort order. Lower numbers sort first.
    providers = [
        {
            'backend': 'google-oauth2',
            'name': 'Google',
            'icon': 'google',
            'priority': -90,
        },
        {
            'backend': 'twitter',
            'name': 'Twitter',
            'icon': 'twitter',
            'priority': 0,
        },
        {
            'backend': 'reddit',
            'name': 'Reddit',
            'icon': 'reddit',
            'priority': 0,
        },
        {
            'backend': 'steam',
            'name': 'Steam',
            'icon': 'steam-square',
            'priority': 0,
        },
        {
            'backend': 'facebook',
            'name': 'Facebook',
            'icon': 'facebook-official',
            'priority': -80,
        },
        {
            'backend': 'flickr',
            'name': 'Flickr',
            'icon': 'flickr',
            'priority': 0,
        },
        {
            'backend': 'github',
            'name': 'GitHub',
            'icon': 'github',
            'priority': 0,
        },
        {
            'backend': 'twitch',
            'name': 'Twitch',
            'icon': 'twitch',
            'priority': 0,
        },
        {
            'backend': 'mit-oidc',
            'name': 'MIT OpenID Connect',
            'icon': 'mit',
            'priority': -1000,
        },
    ]

    enabled_backends = load_backends(settings.AUTHENTICATION_BACKENDS)

    providers = [p for p in providers if p['backend'] in enabled_backends]
    providers = sorted(providers, key=itemgetter('priority', 'name'))

    if backend is not None:
        return next((p for p in providers if p['backend'] == backend), None)

    return providers


def datahub_authenticate(username, password):
    """
    Analog of django.contrib.auth.authenticate.

    Given a username or email plus password, finds the User object, verifies
    the password, and sets a flag on the object allowing it to be used in the
    login function.

    First argument can be a username or email address.

    If the user has an account in a state partially migrated from the legacy
    model, this will finish the migration by setting the password on their
    migrated account and flipping the appropriate flags to allow login.
    """
    # If username looks like an email address, look up the username
    # associated with that address.
    #
    # This assumes the username regex disallows the @ symbol, and the
    # email regex requires it.
    if '@' in username:
        try:
            user = User.objects.get(email=username)
            username = user.username
        except User.DoesNotExist:
            user = None
    else:
        try:
            user = User.objects.get(username=username)
        except:
            user = None
    if user is not None and user.last_login is None:
        hashed_password = hashlib.sha1(password).hexdigest()
        try:
            DataHubLegacyUser.objects.get(
                username=username,
                password=hashed_password)
            print("Found match for {0}".format(username))
            user.set_password(password)
            user.save(update_fields=['password'])
            # Set the user's Postgres password to their hashed password
            DataHubManager.change_password(username, user.password)
            print("Updated password for {0} to {1}".format(username, user.password))
        except DataHubLegacyUser.DoesNotExist:
            print("Nope for {0}".format(username))
            pass

    user = django_authenticate(username=username, password=password)
    return user


def grant_app_permission(username, repo_name, app_id, app_token):
    """
    Grants SELECT, INSERT, UPDATE, and DELETE on given user's repo to app.

    Raises exceptions on empty input, if no app matches app_id, if app_token
    doesn't match, or if there are any database errors.
    """
    if not app_id:
        raise Exception("Invalid app_id")

    if not app_token:
        raise Exception("Invalid app_token")

    app = None
    try:
        app = App.objects.get(app_id=app_id)
    except App.DoesNotExist:
        raise Exception("Invalid app_id")

    if app.app_token != app_token:
        raise Exception("Invalid app_token")

    try:
        manager = DataHubManager(user=username)
        manager.create_repo(repo_name)
        manager.add_collaborator(
            repo_name,
            app_id,
            privileges=['SELECT', 'INSERT', 'UPDATE', 'DELETE'])
    except Exception as e:
        raise e

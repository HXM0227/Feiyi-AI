try:
    from .t2_service.api import create_app
    from .t2_service.config import Settings
except ImportError:
    from t2_service.api import create_app
    from t2_service.config import Settings

app = create_app(Settings.from_env())

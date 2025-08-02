"""
API module with Flask app factory and resource registration
Following diyHue architectural patterns
"""

from services.eventStreamer import stream
from flaskUI.error_pages.handlers import error_pages
from flaskUI.devices.views import devices
from flaskUI.core.views import core
from flask import Flask, Request
from flask_cors import CORS
from flask_restful import Api
from werkzeug.security import check_password_hash
import os
import logging
import logManager
import flask_login
from flaskUI.core import User  # dummy import for flask_login module
import configManager
from flaskUI.restful import NewUser, ShortConfig, EntireConfig, ResourceElements, Element, ElementParam, ElementParamId
from flaskUI.v2restapi import AuthV1, ClipV2, ClipV2Resource, ClipV2ResourceId
from flaskUI.espDevices import Switch
from flaskUI.Credits import Credits

logger: logging.Logger = logManager.logger.get_logger(__name__)


def create_app(bridgeConfig) -> Flask:
    """
    App factory function following diyHue pattern
    """
    root_dir: str = configManager.bridgeConfig.runningDir

    template_dir: str = os.path.join(root_dir, 'flaskUI', 'templates')
    static_dir: str = os.path.join(root_dir, 'flaskUI', 'assets')

    if not os.path.exists(template_dir):
        logger.error(f"Template directory {template_dir} does not exist.")
        raise FileNotFoundError(
            f"Template directory {template_dir} does not exist.")
    if not os.path.exists(static_dir):
        logger.error(f"Static directory {static_dir} does not exist.")
        raise FileNotFoundError(
            f"Static directory {static_dir} does not exist.")
    if "index.html" not in os.listdir(template_dir):
        logger.error(f"index.html not found in {template_dir}.")
        raise FileNotFoundError(f"index.html not found in {template_dir}.")

    app: Flask = Flask(__name__,
                       template_folder=template_dir,
                       static_url_path="/assets",
                       static_folder=static_dir)

    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24))
    app.config['RESTFUL_JSON'] = {'ensure_ascii': False}

    # CORS setup
    cors: CORS = CORS(app, resources={r"*": {"origins": "*"}})

    # Flask-Login setup
    login_manager: flask_login.LoginManager = flask_login.LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "core.login"

    @login_manager.user_loader
    def user_loader(email: str) -> User | None:
        if email not in bridgeConfig["config"]["users"]:
            return None
        user: User = User()
        user.id = email
        return user

    @login_manager.request_loader
    def request_loader(request: Request) -> User | None:
        email: str = request.form.get('email')
        if email not in bridgeConfig["config"]["users"]:
            return None
        user: User = User()
        user.id = email
        logger.info(f"Authentication attempt for user: {email}")
        user.is_authenticated = check_password_hash(
            request.form['password'],
            bridgeConfig["config"]["users"][email]["password"]
        )
        return user

    # Flask-RESTful API setup
    api: Api = Api(app)

    # Licence/credits
    api.add_resource(Credits, '/licenses/<string:resource>', strict_slashes=False)
    # ESP devices
    api.add_resource(Switch, '/switch')
    # HUE API
    api.add_resource(NewUser, '/api/', strict_slashes=False)
    api.add_resource(ShortConfig, '/api/config', strict_slashes=False)
    api.add_resource(EntireConfig, '/api/<string:username>', strict_slashes=False)
    api.add_resource(ResourceElements,
                    '/api/<string:username>/<string:resource>', strict_slashes=False)
    api.add_resource(
        Element, '/api/<string:username>/<string:resource>/<string:resourceid>', strict_slashes=False)
    api.add_resource(
        ElementParam, '/api/<string:username>/<string:resource>/<string:resourceid>/<string:param>/', strict_slashes=False)
    api.add_resource(
        ElementParamId, '/api/<string:username>/<string:resource>/<string:resourceid>/<string:param>/<string:paramid>/', strict_slashes=False)

    # V2 API
    api.add_resource(AuthV1, '/auth/v1', strict_slashes=False)
    # api.add_resource(EventStream, '/eventstream/clip/v2', strict_slashes=False)
    api.add_resource(ClipV2, '/clip/v2/resource', strict_slashes=False)
    api.add_resource(
        ClipV2Resource, '/clip/v2/resource/<string:resource>', strict_slashes=False)
    api.add_resource(ClipV2ResourceId,
                    '/clip/v2/resource/<string:resource>/<string:resourceid>', strict_slashes=False)

    # WEB INTERFACE

    app.register_blueprint(core)
    app.register_blueprint(devices)
    app.register_blueprint(error_pages)
    app.register_blueprint(stream)

    return app

"""Legacy microservice routes for remaining endpoints."""
from flask import Blueprint
from Model.legacy_service import LegacyProfileService as profile

legacyProfileRoute = Blueprint('legacyProfileRoute', __name__, url_prefix='/netwirkProfileRoute')
BLUEPRINTS = (legacyProfileRoute,)


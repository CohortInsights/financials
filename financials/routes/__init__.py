from flask import Blueprint

# Blueprint for all routes
routes_bp = Blueprint('routes', __name__)

# Import individual route groups
from . import dashboard, api_transactions, assign

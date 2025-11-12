# financials/web.py
import argparse
import sys
import tempfile
import logging
from flask import Flask
from financials.utils.services import get_drive_service, get_calculator, set_cache_dir

# Initialize Flask app
app = Flask(__name__)
app.config["DEBUG"] = True

# Configure global logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

# Import route modules (they attach themselves to app via decorators)
import financials.routes.dashboard  # noqa: F401
import financials.routes.api_transactions  # noqa: F401
import financials.routes.assign  # noqa: F401


def main():
    """
    CLI entry point. Creates a temporary cache directory,
    initializes the GoogleDrive client, and runs the Flask app.
    """
    parser = argparse.ArgumentParser(description="Run the Financials web dashboard")
    parser.add_argument('--port', type=int, default=5000, help="Port number to use")
    args = parser.parse_args()

    app.logger.info("Starting Financials web server on port %d", args.port)
    app.logger.debug("Command-line arguments: %s", sys.argv)

    # Initialize Drive + Calculator context and cache dir
    with tempfile.TemporaryDirectory() as data_cache:
        set_cache_dir(data_cache)
        drive = get_drive_service()
        get_calculator(drive)

        with app.app_context():
            setattr(app, 'initialized', True)
            app.run(host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()

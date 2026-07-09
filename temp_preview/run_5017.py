from app import create_app
app = create_app()
app.run(port=5017, debug=False)

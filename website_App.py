import os
import qrcode
import requests
from datetime import datetime
from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy

# ---------------------------------------------------------
# Flask + Datenbank
# ---------------------------------------------------------
app = Flask(__name__, instance_relative_config=True)
app.secret_key = "supersecretkey"

os.makedirs(app.instance_path, exist_ok=True)

db_path = os.path.join(app.instance_path, "database.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ---------------------------------------------------------
# Datenbankmodell
# ---------------------------------------------------------
class Artifact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    inventory_number = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(100))
    era = db.Column(db.String(50))
    material = db.Column(db.String(100))
    dimensions = db.Column(db.String(100))
    storage_location = db.Column(db.String(100))
    description = db.Column(db.Text)
    original_location = db.Column(db.String(200))
    gps_location = db.Column(db.String(100))
    image_path = db.Column(db.String(200))
    qr_code_path = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ---------------------------------------------------------
# Login
# ---------------------------------------------------------
USERNAME = "os-leubnitz"
PASSWORD = "08539"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == USERNAME and request.form.get("password") == PASSWORD:
            session["logged_in"] = True
            return redirect("/")
        return render_template("login.html", error="Falsche Zugangsdaten")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------------------------------------------------
# Startseite
# ---------------------------------------------------------
@app.route("/")
def index():
    if not session.get("logged_in"):
        return redirect("/login")

    artifacts = Artifact.query.all()

    markers = []
    for a in artifacts:
        if a.gps_location:
            try:
                gps_clean = a.gps_location.replace(" ", "")
                lat, lon = map(float, gps_clean.split(","))
                markers.append({
                    "name": a.name,
                    "era": a.era,
                    "original_location": a.original_location,
                    "lat": lat,
                    "lon": lon,
                    "image": a.image_path
                })
            except Exception as e:
                print("Marker-Fehler Startseite:", e)

    return render_template("index.html", artifacts=artifacts, markers=markers)

# ---------------------------------------------------------
# Fund speichern (mit funktionierendem Geocoding)
# ---------------------------------------------------------
@app.route("/save", methods=["POST"])
def save():
    name = request.form.get("name", "").strip()
    era = request.form.get("era", "").strip()
    material = request.form.get("material", "").strip()
    dimensions = request.form.get("dimensions", "").strip()
    storage_location = request.form.get("storage_location", "").strip()
    description = request.form.get("description", "").strip()
    location = request.form.get("location", "").strip()

    original_location = location if location else None
    gps_location = None

    if location:
        # Wenn Text drin ist → Adresse / Stadt / Straße
        if any(c.isalpha() for c in location):
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                "q": location,
                "format": "json",
                "limit": 1,
                "addressdetails": 1
            }
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }

            try:
                response = requests.get(url, params=params, headers=headers, timeout=10)

                # Falls HTML zurückkommt → blockiert
                if response.headers.get("Content-Type", "").startswith("text/html"):
                    print("Nominatim blockiert die Anfrage (HTML statt JSON).")
                    data = []
                else:
                    data = response.json()

                if data:
                    lat = data[0]["lat"]
                    lon = data[0]["lon"]
                    gps_location = f"{lat},{lon}"
                    print("Geocoding erfolgreich:", gps_location)
                else:
                    print("Keine Geocoding-Daten gefunden für:", location)

            except Exception as e:
                print("Geocoding Fehler:", e)

        # Wenn nur Zahlen/Komma → Koordinaten direkt
        else:
            gps_location = location.replace(" ", "")

    # Bild speichern
    image = request.files.get("image")
    image_path = None
    if image and image.filename:
        filename = f"{os.urandom(8).hex()}_{image.filename}"
        upload_dir = os.path.join("static", "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        upload_path = os.path.join(upload_dir, filename)
        image.save(upload_path)
        image_path = f"static/uploads/{filename}"

    # Inventarnummer
    count = Artifact.query.count() + 1
    inventory_number = f"INV-{count:06d}"

    # QR-Code
    qr_img = qrcode.make(inventory_number)
    qr_dir = os.path.join("static", "qrcodes")
    os.makedirs(qr_dir, exist_ok=True)
    qr_filename = f"{inventory_number}.png"
    qr_path = os.path.join(qr_dir, qr_filename)
    qr_img.save(qr_path)
    qr_code_path = f"static/qrcodes/{qr_filename}"

    # Speichern
    artifact = Artifact(
        inventory_number=inventory_number,
        name=name,
        era=era,
        material=material or None,
        dimensions=dimensions or None,
        storage_location=storage_location or None,
        description=description or None,
        original_location=original_location,
        gps_location=gps_location,
        image_path=image_path,
        qr_code_path=qr_code_path
    )

    db.session.add(artifact)
    db.session.commit()

    return redirect("/")

# ---------------------------------------------------------
# Detailseite (mit Marker)
# ---------------------------------------------------------
@app.route("/artifact/<int:id>")
def artifact_detail(id):
    artifact = Artifact.query.get_or_404(id)

    marker = None
    if artifact.gps_location:
        try:
            gps_clean = artifact.gps_location.replace(" ", "")
            lat, lon = map(float, gps_clean.split(","))
            marker = {
                "lat": lat,
                "lon": lon,
                "name": artifact.name,
                "era": artifact.era,
                "original_location": artifact.original_location,
                "image": artifact.image_path
            }
        except Exception as e:
            print("Marker-Fehler Detail:", e)
            marker = None

    return render_template("artifact_detail.html", artifact=artifact, marker=marker)

# ---------------------------------------------------------
# Löschen
# ---------------------------------------------------------
@app.route("/delete/<int:id>")
def delete(id):
    artifact = Artifact.query.get_or_404(id)

    if artifact.image_path:
        try:
            os.remove(artifact.image_path)
        except Exception as e:
            print("Bild löschen Fehler:", e)

    if artifact.qr_code_path:
        try:
            os.remove(artifact.qr_code_path)
        except Exception as e:
            print("QR löschen Fehler:", e)

    db.session.delete(artifact)
    db.session.commit()

    return redirect("/")

# ---------------------------------------------------------
# Suche
# ---------------------------------------------------------
@app.route("/search")
def search():
    q = request.args.get("q", "")
    results = Artifact.query.filter(
        Artifact.name.ilike(f"%{q}%") |
        Artifact.era.ilike(f"%{q}%") |
        Artifact.material.ilike(f"%{q}%") |
        Artifact.storage_location.ilike(f"%{q}%")
    ).all()

    return render_template("index.html", artifacts=results, markers=[], search_query=q)

# ---------------------------------------------------------
# Filter
# ---------------------------------------------------------
@app.route("/filter")
def filter():
    era = request.args.get("era")
    material = request.args.get("material")
    storage = request.args.get("storage")

    query = Artifact.query

    if era:
        query = query.filter_by(era=era)
    if material:
        query = query.filter(Artifact.material.ilike(f"%{material}%"))
    if storage:
        query = query.filter(Artifact.storage_location.ilike(f"%{storage}%"))

    results = query.all()

    return render_template("index.html", artifacts=results, markers=[])

# ---------------------------------------------------------
# Start
# ---------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

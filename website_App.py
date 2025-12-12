from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests
import os

app = Flask(__name__)

# GEHEIMSCHLÜSSEL FÜR SESSION (ÄNDERN!)
app.secret_key = "BITTE_HIER_EIN_EIGENES_GEHEIMES_PASSWORT_EINTRAGEN"

# Login-Daten (kannst du ändern)
USERNAME = "admin"
PASSWORD = "scard123"

# Datenbank
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Upload-Ordner
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)


# -----------------------------
# Datenbankmodell
# -----------------------------
class Artifact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    era = db.Column(db.String(100))
    original_location = db.Column(db.String(200))   # Eingabe (z.B. "Zwickau")
    gps_location = db.Column(db.String(200))        # "lat, lon"
    description = db.Column(db.Text)
    image_path = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# -----------------------------
# Login-System
# -----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("username")
        pw = request.form.get("password")

        if user == USERNAME and pw == PASSWORD:
            session["logged_in"] = True
            return redirect("/")
        else:
            return render_template("login.html", error="Falsche Zugangsdaten")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


def login_required(f):
    # Kleiner Wrapper, der prüft, ob eingeloggt
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


# -----------------------------
# Geocoding (Ortsname → GPS)
# -----------------------------
def geocode_location(location_text: str):
    if not location_text:
        return None

    text = location_text.strip()

    # Wenn schon Koordinaten drin sind
    if "," in text:
        parts = text.replace(";", ",").split(",")
        if len(parts) == 2:
            try:
                lat = float(parts[0].strip().replace(",", "."))
                lon = float(parts[1].strip().replace(",", "."))
                return f"{lat:.5f}, {lon:.5f}"
            except ValueError:
                pass

    # Sonst: Geocoding über OpenStreetMap
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": location_text, "format": "json", "limit": 1}
        headers = {"User-Agent": "ScardScopes-Archaeology-App"}

        response = requests.get(url, params=params, headers=headers, timeout=5)
        data = response.json()

        if not data:
            return None

        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return f"{lat:.5f}, {lon:.5f}"
    except Exception as e:
        print("Geocoding-Fehler:", e)
        return None


# -----------------------------
# Hauptseite (nur eingeloggt)
# -----------------------------
@app.route("/")
@login_required
def index():
    artifacts = Artifact.query.order_by(Artifact.created_at.desc()).all()

    # Marker für Karte
    markers = []
    for a in artifacts:
        if a.gps_location and "," in a.gps_location:
            try:
                lat, lon = a.gps_location.split(",")
                markers.append({
                    "name": a.name,
                    "era": a.era,
                    "lat": float(lat.strip()),
                    "lon": float(lon.strip()),
                    "image": a.image_path,
                    "original_location": a.original_location
                })
            except Exception as e:
                print("Marker-Fehler:", e)
                continue

    return render_template("index.html", artifacts=artifacts, markers=markers)


# -----------------------------
# Fund speichern
# -----------------------------
@app.route("/save", methods=["POST"])
@login_required
def save():
    name = request.form.get("name")
    era = request.form.get("era")
    original_location = request.form.get("location")
    description = request.form.get("description")

    gps_location = geocode_location(original_location)

    image = request.files.get("image")
    image_path = None

    if image and image.filename != "":
        filename = f"{datetime.utcnow().timestamp()}_{image.filename}"
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        image.save(save_path)
        image_path = save_path

    new_artifact = Artifact(
        name=name,
        era=era,
        original_location=original_location,
        gps_location=gps_location,
        description=description,
        image_path=image_path
    )

    db.session.add(new_artifact)
    db.session.commit()

    return redirect("/")


# -----------------------------
# Fund löschen
# -----------------------------
@app.route("/delete/<int:id>")
@login_required
def delete(id):
    artifact = Artifact.query.get_or_404(id)

    if artifact.image_path and os.path.exists(artifact.image_path):
        os.remove(artifact.image_path)

    db.session.delete(artifact)
    db.session.commit()

    return redirect("/")


# -----------------------------
# App starten
# -----------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)

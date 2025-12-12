from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests
import qrcode
import os

app = Flask(__name__)
app.secret_key = "DEIN_GEHEIMER_SCHLUESSEL"

USERNAME = "admin"
PASSWORD = "scard123"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

UPLOAD_FOLDER = "static/uploads"
QR_FOLDER = "static/qrcodes"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

db = SQLAlchemy(app)


# ---------------------------------------------------------
# Datenbankmodell
# ---------------------------------------------------------
class Artifact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    era = db.Column(db.String(100))
    material = db.Column(db.String(100))
    inventory_number = db.Column(db.String(50), unique=True)
    dimensions = db.Column(db.String(100))
    storage_location = db.Column(db.String(200))
    original_location = db.Column(db.String(200))
    gps_location = db.Column(db.String(200))
    description = db.Column(db.Text)
    image_path = db.Column(db.String(300))
    qr_path = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------------------------------------------------------
# Inventarnummer generieren
# ---------------------------------------------------------
def generate_inventory_number():
    last = Artifact.query.order_by(Artifact.id.desc()).first()
    if not last or not last.inventory_number:
        return "INV-000001"

    try:
        prefix, num = last.inventory_number.split("-")
        return f"{prefix}-{int(num) + 1:06d}"
    except:
        return "INV-000001"


# ---------------------------------------------------------
# QR-Code erzeugen
# ---------------------------------------------------------
def generate_qr_code(text, filename):
    path = os.path.join(QR_FOLDER, filename)
    img = qrcode.make(text)
    img.save(path)
    return path


# ---------------------------------------------------------
# Login
# ---------------------------------------------------------
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


def login_required(f):
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


# ---------------------------------------------------------
# Geocoding
# ---------------------------------------------------------
def geocode_location(text: str):
    if not text:
        return None

    text = text.strip()

    if "," in text:
        try:
            lat, lon = text.split(",")
            return f"{float(lat):.5f}, {float(lon):.5f}"
        except:
            pass

    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": text, "format": "json", "limit": 1}
        headers = {"User-Agent": "ScardScopes-App"}
        r = requests.get(url, params=params, headers=headers, timeout=5)
        data = r.json()
        if not data:
            return None
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return f"{lat:.5f}, {lon:.5f}"
    except:
        return None


# ---------------------------------------------------------
# Startseite
# ---------------------------------------------------------
@app.route("/")
@login_required
def index():
    artifacts = Artifact.query.order_by(Artifact.created_at.desc()).all()

    markers = []
    for a in artifacts:
        if a.gps_location and "," in a.gps_location:
            try:
                lat, lon = a.gps_location.split(",")
                markers.append({
                    "name": a.name,
                    "era": a.era,
                    "lat": float(lat),
                    "lon": float(lon),
                    "image": a.image_path,
                    "original_location": a.original_location
                })
            except:
                continue

    return render_template("index.html",
                           artifacts=artifacts,
                           markers=markers,
                           search_query=None)


# ---------------------------------------------------------
# Suche
# ---------------------------------------------------------
@app.route("/search")
@login_required
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return redirect("/")

    results = Artifact.query.filter(
        db.or_(
            Artifact.name.ilike(f"%{q}%"),
            Artifact.inventory_number.ilike(f"%{q}%"),
            Artifact.material.ilike(f"%{q}%"),
            Artifact.era.ilike(f"%{q}%"),
            Artifact.storage_location.ilike(f"%{q}%"),
            Artifact.original_location.ilike(f"%{q}%"),
        )
    ).order_by(Artifact.created_at.desc()).all()

    markers = []
    for a in results:
        if a.gps_location and "," in a.gps_location:
            try:
                lat, lon = a.gps_location.split(",")
                markers.append({
                    "name": a.name,
                    "era": a.era,
                    "lat": float(lat),
                    "lon": float(lon),
                    "image": a.image_path,
                    "original_location": a.original_location
                })
            except:
                continue

    return render_template("index.html",
                           artifacts=results,
                           markers=markers,
                           search_query=q)


# ---------------------------------------------------------
# Filter
# ---------------------------------------------------------
@app.route("/filter")
@login_required
def filter_artifacts():
    era = request.args.get("era", "")
    material = request.args.get("material", "")
    storage = request.args.get("storage", "")

    query = Artifact.query

    if era:
        query = query.filter(Artifact.era == era)

    if material:
        query = query.filter(Artifact.material.ilike(f"%{material}%"))

    if storage:
        query = query.filter(Artifact.storage_location.ilike(f"%{storage}%"))

    results = query.order_by(Artifact.created_at.desc()).all()

    markers = []
    for a in results:
        if a.gps_location and "," in a.gps_location:
            try:
                lat, lon = a.gps_location.split(",")
                markers.append({
                    "name": a.name,
                    "era": a.era,
                    "lat": float(lat),
                    "lon": float(lon),
                    "image": a.image_path,
                    "original_location": a.original_location
                })
            except:
                continue

    return render_template("index.html",
                           artifacts=results,
                           markers=markers,
                           search_query=None)


# ---------------------------------------------------------
# Detailseite
# ---------------------------------------------------------
@app.route("/artifact/<int:id>")
@login_required
def artifact_detail(id):
    artifact = Artifact.query.get_or_404(id)

    marker = None
    if artifact.gps_location and "," in artifact.gps_location:
        try:
            lat, lon = artifact.gps_location.split(",")
            marker = {
                "lat": float(lat),
                "lon": float(lon),
                "name": artifact.name,
                "era": artifact.era,
                "original_location": artifact.original_location,
                "image": artifact.image_path
            }
        except:
            marker = None

    return render_template("artifact_detail.html",
                           artifact=artifact,
                           marker=marker)


# ---------------------------------------------------------
# Speichern
# ---------------------------------------------------------
@app.route("/save", methods=["POST"])
@login_required
def save():
    name = request.form.get("name")
    era = request.form.get("era")
    material = request.form.get("material")
    dimensions = request.form.get("dimensions")
    storage_location = request.form.get("storage_location")
    original_location = request.form.get("location")
    description = request.form.get("description")

    gps_location = geocode_location(original_location)

    image = request.files.get("image")
    image_path = None
    if image and image.filename:
        filename = f"{datetime.utcnow().timestamp()}_{image.filename}"
        path = os.path.join(UPLOAD_FOLDER, filename)
        image.save(path)
        image_path = path

    inv = generate_inventory_number()

    a = Artifact(
        name=name,
        era=era,
        material=material,
        inventory_number=inv,
        dimensions=dimensions,
        storage_location=storage_location,
        original_location=original_location,
        gps_location=gps_location,
        description=description,
        image_path=image_path
    )

    db.session.add(a)
    db.session.commit()

    qr_text = f"http://localhost:5000/artifact/{a.id}"
    qr_filename = f"{a.inventory_number}.png"
    qr_path = generate_qr_code(qr_text, qr_filename)

    a.qr_path = qr_path
    db.session.commit()

    return redirect("/")


# ---------------------------------------------------------
# Löschen
# ---------------------------------------------------------
@app.route("/delete/<int:id>")
@login_required
def delete(id):
    a = Artifact.query.get_or_404(id)

    if a.image_path and os.path.exists(a.image_path):
        try:
            os.remove(a.image_path)
        except:
            pass

    if a.qr_path and os.path.exists(a.qr_path):
        try:
            os.remove(a.qr_path)
        except:
            pass

    db.session.delete(a)
    db.session.commit()
    return redirect("/")


# ---------------------------------------------------------
# Start
# ---------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)

import os
import qrcode
import requests
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Datenbank in /instance/database.db
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
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


# ---------------------------------------------------------
# Login-System
# ---------------------------------------------------------
USERNAME = "admin"
PASSWORD = "1234"


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["username"] == USERNAME and request.form["password"] == PASSWORD:
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

    # Marker für Karte
    markers = []
    for a in artifacts:
        if a.gps_location:
            try:
                lat, lon = map(float, a.gps_location.split(","))
                markers.append({
                    "name": a.name,
                    "era": a.era,
                    "original_location": a.original_location,
                    "lat": lat,
                    "lon": lon,
                    "image": a.image_path
                })
            except:
                pass

    return render_template("index.html", artifacts=artifacts, markers=markers)


# ---------------------------------------------------------
# Fund speichern
# ---------------------------------------------------------
@app.route("/save", methods=["POST"])
def save():
    name = request.form["name"]
    era = request.form["era"]
    material = request.form.get("material")
    dimensions = request.form.get("dimensions")
    storage_location = request.form.get("storage_location")
    description = request.form.get("description")
    location = request.form.get("location")

    # GPS extrahieren
    gps_location = None
    original_location = location

    if "," in location:
        gps_location = location
    else:
        # Geocoding
        url = f"https://nominatim.openstreetmap.org/search?q={location}&format=json"
        r = requests.get(url).json()
        if r:
            gps_location = f"{r[0]['lat']}, {r[0]['lon']}"

    # Bild speichern
    image = request.files.get("image")
    image_path = None
    if image:
        filename = f"{str(os.urandom(8).hex())}_{image.filename}"
        upload_path = os.path.join("static/uploads", filename)
        image.save(upload_path)
        image_path = f"/static/uploads/{filename}"

    # Inventarnummer erzeugen
    count = Artifact.query.count() + 1
    inventory_number = f"INV-{count:06d}"

    # QR-Code erzeugen
    qr_img = qrcode.make(inventory_number)
    qr_filename = f"{inventory_number}.png"
    qr_path = os.path.join("static/qrcodes", qr_filename)
    qr_img.save(qr_path)

    qr_code_path = f"/static/qrcodes/{qr_filename}"

    # In DB speichern
    artifact = Artifact(
        inventory_number=inventory_number,
        name=name,
        era=era,
        material=material,
        dimensions=dimensions,
        storage_location=storage_location,
        description=description,
        original_location=original_location,
        gps_location=gps_location,
        image_path=image_path,
        qr_code_path=qr_code_path
    )

    db.session.add(artifact)
    db.session.commit()

    return redirect("/")


# ---------------------------------------------------------
# Detailseite
# ---------------------------------------------------------
@app.route("/artifact/<int:id>")
def artifact_detail(id):
    artifact = Artifact.query.get_or_404(id)
    return render_template("artifact_detail.html", a=artifact)


# ---------------------------------------------------------
# Löschen
# ---------------------------------------------------------
@app.route("/delete/<int:id>")
def delete(id):
    artifact = Artifact.query.get_or_404(id)

    # Bild löschen
    if artifact.image_path:
        try:
            os.remove(artifact.image_path[1:])
        except:
            pass

    # QR-Code löschen
    if artifact.qr_code_path:
        try:
            os.remove(artifact.qr_code_path[1:])
        except:
            pass

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
# Render / Heroku PORT-FIX
# ---------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

from flask import Flask, render_template, request, redirect, session
import sqlite3, os
import cv2, numpy as np, h5py
from skimage.color import rgb2gray
from skimage.io import imread
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # Required for session

# ------------------ DB ------------------
def get_db():
    return sqlite3.connect("users.db")

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ------------------ FOLDERS ------------------
UPLOAD_FOLDER = "static/uploads"
RESULT_FOLDER = "static/results"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

# ------------------ HENON MAP ------------------
def henon_map(a=1.4, b=0.3, size=64*64, x0=0.1, y0=0.1):
    x, y = np.zeros(size), np.zeros(size)
    x[0], y[0] = x0, y0
    for i in range(1, size):
        x[i] = y[i-1] + 1 - a*(x[i-1]**2)
        y[i] = b*x[i-1]
    seq = np.abs(x * 10**14) % 256
    return seq.reshape(64, 64).astype(np.uint8)

# ------------------ WATERMARK ------------------
watermark = np.zeros((64,64),dtype=np.uint8)
cv2.putText(watermark,"HOSP",(5,40),
            cv2.FONT_HERSHEY_SIMPLEX,1.3,255,2)
chaotic_seq = henon_map()

# ------------------ ROUTES ------------------
@app.route('/')
def home():
    return render_template("home.html")

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=? AND password=?", (u,p))
        user = cur.fetchone()
        conn.close()

        if user:
            session['username'] = u
            return redirect('/index')
        else:
            return "<h3 style='color:red;text-align:center'>Invalid Username or Password ❌</h3>"

    return render_template("login.html")

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']

        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users(username,password) VALUES (?,?)",
                (u,p)
            )
            conn.commit()
            conn.close()
            return redirect('/login')
        except:
            return "<h3 style='color:red;text-align:center'>Username already exists ❌</h3>"

    return render_template("register.html")

@app.route('/index')
def index():
    if 'username' not in session:
        return redirect('/login')
    return render_template("index.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')  # Direct home page, no message

# ------------------ GENERATE ------------------
@app.route('/generate', methods=['POST'])
def generate():
    if 'username' not in session:
        return redirect('/login')

    file = request.files['file']
    path = os.path.join(UPLOAD_FOLDER,file.filename)
    file.save(path)

    img = imread(path)
    gray = rgb2gray(img) if len(img.shape)==3 else img
    gray = cv2.resize((gray*255).astype(np.uint8),(256,256))

    dct = cv2.dct(np.float32(gray))
    fv = (dct[:64,:64] > np.mean(dct)).astype(np.uint8)

    encrypted = cv2.bitwise_xor(watermark, chaotic_seq)
    zw = cv2.bitwise_xor(fv*255, encrypted)

    zw_path = os.path.join(RESULT_FOLDER,"zero.png")
    cv2.imwrite(zw_path, zw)

    return render_template(
        "result.html",
        image_path=path,
        watermark_path=zw_path,
        message="Zero Watermark Generated Successfully ✅"
    )

# ------------------ VERIFY ------------------
@app.route('/verify', methods=['POST'])
def verify():
    if 'username' not in session:
        return redirect('/login')

    test = request.files['test_file']
    wm   = request.files['wm_file']

    tpath = os.path.join(UPLOAD_FOLDER,test.filename)
    wpath = os.path.join(UPLOAD_FOLDER,wm.filename)
    test.save(tpath)
    wm.save(wpath)

    img = imread(tpath)
    gray = rgb2gray(img) if len(img.shape)==3 else img
    gray = cv2.resize((gray*255).astype(np.uint8),(256,256))

    dct = cv2.dct(np.float32(gray))
    fv = (dct[:64,:64] > np.mean(dct)).astype(np.uint8)

    stored = cv2.imread(wpath,0)
    stored = cv2.resize(stored,(64,64))

    encrypted = cv2.bitwise_xor(watermark, chaotic_seq)
    current = cv2.bitwise_xor(fv*255, encrypted)

    nc = np.sum(current==stored)/(64*64)
    ber = 1-nc

    plt.figure()
    plt.bar(["NC","BER"],[nc,ber])
    plt.savefig("static/results/chart.png")
    plt.close()

    status = "Authentic ✅" if nc>0.95 else "Tampered ❌"

    return render_template(
        "result.html",
        image_path=tpath,
        watermark_path=wpath,
        message=f"{status} | NC={nc:.3f} BER={ber:.3f}"
    )

@app.route('/chart')
def chart():
    if 'username' not in session:
        return redirect('/login')
    return render_template("chart.html")

# ------------------ MAIN ------------------
if __name__ == "__main__":
    app.run(debug=True)

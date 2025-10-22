from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from psycopg.errors import UniqueViolation 
import psycopg
import bcrypt
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
import os

# --- Inicializar la app primero ---
# --- Inicializar la app primero ---
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'clave_predeterminada_segura')  # 🔹 Usar variable de entorno en Render

# --- Configuración del correo ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')  # 🔹 Gmail o correo configurado
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')  # 🔹 Contraseña o app password de Gmail
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', 'soporte.farmaciasantarosa@gmail.com')

# --- Inicializar extensiones ---
mail = Mail(app)
s = URLSafeTimedSerializer(app.secret_key)

def get_db_connection():
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://farmacia:...@host/farmacia_q46p"
    )
    conn = psycopg.connect(DATABASE_URL, autocommit=True, row_factory=psycopg.rows.dict_row)
    return conn

# --- Cierre de sesión ---
@app.route('/logout')
def logout():
    session.pop('usuario', None)
    flash('Sesión cerrada correctamente.', 'success')
    return redirect(url_for('index'))


# --- Inicio de sesión ---
@app.route('/login', methods=['POST'])
def login():
    correo = request.form['correo']
    contrasena = request.form['password']

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT * FROM cliente WHERE correo_electronico = %s"
            cursor.execute(sql, (correo,))
            user = cursor.fetchone()

            if user and bcrypt.checkpw(contrasena.encode('utf-8'), user['contrasena'].encode('utf-8')):
                if user.get('verificado') == 0:
                    flash('Debes verificar tu correo antes de iniciar sesión.', 'warning')
                else:
                    session['usuario'] = user['nombre']
                    session['usuario_id'] = user['id_cliente']
                    flash('Inicio de sesión exitoso.', 'success')
            else:
                flash('Correo o contraseña incorrectos.', 'danger')
    finally:
        connection.close()

    return redirect(url_for('index'))


# --- Perfil ---
@app.route('/perfil', methods=['GET', 'POST'])
def perfil():
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión para acceder al perfil.', 'warning')
        return redirect(url_for('index', _anchor='loginModal'))

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        nombre = request.form['nombre']
        apellido = request.form['apellido']
        telefono = request.form['telefono']
        direccion = request.form['direccion']

        cursor.execute('''
            UPDATE cliente 
            SET nombre = %s, apellido = %s, telefono = %s, direccion = %s 
            WHERE id_cliente = %s
        ''', (nombre, apellido, telefono, direccion, session['usuario_id']))
        conn.commit()
        flash("Perfil actualizado correctamente", "success")

    cursor.execute('SELECT * FROM cliente WHERE id_cliente = %s', (session['usuario_id'],))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template('perfil.html', data={
        'name': f"{user['nombre']} {user['apellido']}",
        'email': user['correo_electronico'],
        'phone': user['telefono'],
        'address': user['direccion'],
        'bio': 'Aquí puedes escribir tu biografía.',
        'profile_image': None
    })


# --- Confirmación de correo ---
@app.route('/confirmar/<token>')
def confirmar_correo(token):
    try:
        email = s.loads(token, salt='email-confirm', max_age=3600)
    except SignatureExpired:
        return 'El enlace de verificación ha expirado.'
    except Exception:
        return 'Enlace inválido.'

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE cliente SET verificado = 1 WHERE correo_electronico = %s", (email,))
            connection.commit()
    finally:
        connection.close()

    flash('Tu correo ha sido verificado correctamente.', 'success')
    return redirect(url_for('index'))


# --- Registro ---
@app.route('/registro', methods=['POST'])
def registro():
    nombre = request.form['nombre']
    apellido = request.form['apellido']
    email = request.form['email']
    password = request.form['password']
    telefono = request.form['telefono']
    direccion = request.form['direccion']

    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
                INSERT INTO cliente (nombre, apellido, correo_electronico, contrasena, telefono, direccion, verificado)
                VALUES (%s, %s, %s, %s, %s, %s, 0)
            """
            cursor.execute(sql, (nombre, apellido, email, hashed.decode('utf-8'), telefono, direccion))
            connection.commit()

        # --- Enviar correo de verificación ---
        token = s.dumps(email, salt='email-confirm')
        link = url_for('confirmar_correo', token=token, _external=True)

        msg = Message('Confirma tu cuenta en FarmaciaApp', recipients=[email])
        msg.body = f'Hola {nombre}, haz clic en este enlace para verificar tu cuenta:\n\n{link}'
        mail.send(msg)

        flash('✅ Registro exitoso. Revisa tu correo para verificar tu cuenta.', 'success')
        return redirect(url_for('index'))

    except UniqueViolation:
        flash('⚠️ El correo ya está registrado. Intenta con otro o inicia sesión.', 'danger')
        return redirect(url_for('index'))


    except Exception as e:
        # 🔹 Cualquier otro error inesperado
        print("Error durante el registro:", e)
        flash('❌ Ocurrió un error inesperado. Intenta nuevamente.', 'danger')
        return redirect(url_for('index'))

    finally:
        connection.close()


@app.route('/carrito')
def carrito():
    return "Aquí va la página del carrito"


@app.route('/categorias')
def categorias():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM categories WHERE activo=1")
            categorias = cursor.fetchall()
    finally:
        connection.close()
    return render_template('categorias.html', categorias=categorias)
@app.route('/')
def index():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Categorías
            cursor.execute("SELECT id_categoria, nombre FROM categories WHERE activo = 1")
            categories = cursor.fetchall()

            # Productos
            cursor.execute("""
                SELECT product_id, product_name, product_image, brand_name, rate, mrp
                FROM product
                JOIN brands ON product.brand_id = brands.brand_id
                WHERE active = 1
            """)
            products = cursor.fetchall()

            # Banners tipo 'carrusel'
            cursor.execute("""
                SELECT imagen FROM banners 
                WHERE activo = 1 AND tipo = 'carrusel'
                ORDER BY orden ASC
            """)
            banners_carrusel = cursor.fetchall()

            # Banners tipo 'banner' (intercalados entre productos)
            cursor.execute("""
                SELECT imagen FROM banners 
                WHERE activo = 1 AND tipo = 'banner'
                ORDER BY orden ASC
            """)
            banners_estaticos = cursor.fetchall()

    finally:
        connection.close()

    return render_template('index.html',
        categories=categories,
        products=products,
        banners_carrusel=banners_carrusel,
        banners_estaticos=banners_estaticos
    )

@app.route('/categorias-json')
def categorias_json():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id_categoria, nombre FROM categories")
            categorias = cursor.fetchall()
    finally:
        connection.close()

    return jsonify(categorias)



@app.route('/subcategorias')
def subcategorias():
    id_categoria = request.args.get('id_categoria')
    if not id_categoria:
        return jsonify([])  # Retorna lista vacía si no hay id_categoria

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id_subcategoria, nombre FROM subcategorias WHERE id_categoria = %s",
                (id_categoria,)
            )
            subs = cursor.fetchall()
    finally:
        connection.close()

    return jsonify(subs)

@app.route('/subcategoria/<int:id_subcategoria>')
def mostrar_productos_subcategoria(id_subcategoria):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT product_id, product_name, product_image, rate, mrp
                FROM product
                WHERE subcategoria_id = %s
            """, (id_subcategoria,))
            productos = cursor.fetchall()

            cursor.execute(
                "SELECT nombre FROM subcategorias WHERE id_subcategoria = %s",
                (id_subcategoria,)
            )
            sub = cursor.fetchone()
    finally:
        connection.close()

    if not sub:
        return "Subcategoría no encontrada", 404

    return render_template(
        'productos_subcategoria.html',
        subcategoria=sub['nombre'],
        productos=productos
    )

@app.route('/checkout')
def checkout():
    # 🔹 Simulación de carrito (en la práctica, lo traerías de la base de datos o la sesión)
    carrito = [
        {'nombre': 'Paracetamol 500mg', 'cantidad': 2, 'precio': 3.5},
        {'nombre': 'Alcohol en gel 250ml', 'cantidad': 1, 'precio': 6.0},
        {'nombre': 'Mascarilla KN95', 'cantidad': 3, 'precio': 2.5}
    ]

    subtotal = sum(i['cantidad'] * i['precio'] for i in carrito)
    envio = 5.0 if subtotal < 50 else 0
    total = subtotal + envio

    return render_template('checkout.html',
                           carrito=carrito,
                           subtotal=subtotal,
                           envio=envio,
                           total=total)


@app.route('/procesar_compra', methods=['POST'])
def procesar_compra():
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión para continuar', 'warning')
        return redirect(url_for('index', _anchor='loginModal'))

    user_id = session['usuario_id']
    metodo_pago = request.form['metodo_pago']
    comentarios = request.form.get('comentarios', '')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT p.product_id, p.mrp AS precio, c.cantidad
        FROM carrito c
        JOIN product p ON c.id_producto = p.product_id
        WHERE c.id_cliente = %s
    """, (user_id,))
    productos = cursor.fetchall()

    if not productos:
        flash('Tu carrito está vacío.', 'warning')
        return redirect(url_for('carrito'))

    total = sum(p['precio'] * p['cantidad'] for p in productos)

    cursor.execute("""
        INSERT INTO orders (client_id, total_amount, payment_method, notes)
        VALUES (%s, %s, %s, %s)
    """, (user_id, total, metodo_pago, comentarios))
    cursor.execute("SELECT LASTVAL()")
    order_id = cursor.fetchone()['lastval']

    for p in productos:
        cursor.execute("""
            INSERT INTO order_item (order_id, product_id, quantity)
            VALUES (%s, %s, %s)
        """, (order_id, p['product_id'], p['cantidad']))

    cursor.execute("DELETE FROM carrito WHERE id_cliente = %s", (user_id,))

    conn.commit()
    conn.close()

    flash('Compra finalizada correctamente 🎉', 'success')
    return redirect(url_for('index'))


@app.route('/buscar_productos', methods=['GET'])
def buscar_productos():
    termino = request.args.get('q', '').strip()
    if not termino:
        flash('Ingresa una palabra clave para buscar.', 'warning')
        return redirect(url_for('index'))

    conexion = get_db_connection()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT
                  p.product_id,
                  p.product_name,
                  p.product_image,
                  b.brand_name,
                  p.rate,
                  p.mrp
                FROM product p
                JOIN brands b ON p.brand_id = b.brand_id
                WHERE p.product_name LIKE %s
                   OR b.brand_name   LIKE %s
            """, (f"%{termino}%", f"%{termino}%"))
            productos = cursor.fetchall()
    finally:
        conexion.close()

    if not productos:
        flash(f"No se encontraron productos para “{termino}”.", "warning")

    return render_template(
        'buscar_resultados.html',  # debe coincidir con el nombre de tu archivo
        productos=productos,
        termino=termino
    )
if __name__ == '__main__':
    app.run(debug=True, port=5000)

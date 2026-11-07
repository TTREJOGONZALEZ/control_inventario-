
from flask import Flask, jsonify, render_template, request, redirect, url_for, flash
from flask_bcrypt import Bcrypt
from mysql.connector import Error
from db import conectar_db
import re
import os
from dotenv import load_dotenv
from flask import session

from decimal import Decimal, InvalidOperation

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]

bcrypt = Bcrypt(app)


@app.route("/")
def inicio():
    if "id_usuario" not in session:
        return redirect(url_for("login"))

    id_negocio = session["id_negocio"]
    conexion = None
    cursor = None

    try:
        conexion = conectar_db()
        cursor = conexion.cursor(dictionary=True)

        # Total de ingresos por ventas
        cursor.execute("""
            SELECT COALESCE(SUM(importe_total), 0) AS total
            FROM ventas
            WHERE id_negocio = %s
        """, (id_negocio,))
        ventas_totales = cursor.fetchone()["total"]

        # Productos activos registrados
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM productos
            WHERE id_negocio = %s AND activo = TRUE
        """, (id_negocio,))
        total_productos = cursor.fetchone()["total"]

        # Pedidos registrados
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM pedidos
            WHERE id_negocio = %s
        """, (id_negocio,))
        total_pedidos = cursor.fetchone()["total"]

        # Productos con stock bajo o agotados
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM v_alertas_stock
            WHERE id_negocio = %s
        """, (id_negocio,))
        total_alertas = cursor.fetchone()["total"]

        return render_template(
            "index.html",
            nombre_usuario=session["nombre"],
            ventas_totales=ventas_totales,
            total_productos=total_productos,
            total_pedidos=total_pedidos,
            total_alertas=total_alertas
        )

    except Error:
        app.logger.exception("Error al consultar el Dashboard")
        return "No se pudo cargar el Dashboard.", 500

    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()


@app.route("/probar-db")
def probar_db():
    try:
        conexion = conectar_db()
        cursor = conexion.cursor()

        cursor.execute("SELECT DATABASE()")
        resultado = cursor.fetchone()

        cursor.close()
        conexion.close()

        return jsonify({
            "estado": "Conectado correctamente",
            "base_de_datos": resultado[0]
        })

    except Exception:
        app.logger.exception("Error de conexión a MySQL")
        return jsonify({
            "estado": "Error al conectar con MySQL"
        }), 500


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        negocio = request.form.get("negocio", "").strip()
        espacio = request.form.get("espacio", "").strip().lower()
        correo = request.form.get("correo", "").strip().lower()
        password = request.form.get("password", "")

        if not all([nombre, negocio, espacio, correo, password]):
            flash("Completa todos los campos.", "error")
            return redirect(url_for("registro"))

        if len(password) < 8:
            flash("La contraseña debe tener mínimo 8 caracteres.", "error")
            return redirect(url_for("registro"))

        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", espacio):
            flash("El espacio de trabajo solo puede tener letras minúsculas, números y guiones.", "error")
            return redirect(url_for("registro"))

        conexion = None
        cursor = None

        try:
            password_hash = bcrypt.generate_password_hash(
                password
            ).decode("utf-8")

            conexion = conectar_db()
            cursor = conexion.cursor()

            cursor.callproc("sp_registrar_negocio", [
                negocio,
                espacio,
                nombre,
                correo,
                password_hash
            ])

            conexion.commit()

            flash("¡Cuenta creada correctamente!", "success")
            return redirect(url_for("registro"))

        except Error as error:
            app.logger.error("Error al registrar negocio: %s", error)

            if error.errno == 1062:
                flash("El correo o espacio de trabajo ya está registrado.", "error")
            else:
                flash("No se pudo crear la cuenta. Intenta nuevamente.", "error")

        finally:
            if cursor is not None:
                cursor.close()
            if conexion is not None and conexion.is_connected():
                conexion.close()

        return redirect(url_for("registro"))

    return render_template("registro.html")



@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        password = request.form.get("password", "")

        conexion = None
        cursor = None

        try:
            conexion = conectar_db()
            cursor = conexion.cursor(dictionary=True)

            cursor.execute("""
                SELECT id_usuario, id_negocio, nombre,
                       correo, password_hash, rol
                FROM usuarios
                WHERE correo = %s AND activo = TRUE
            """, (correo,))

            usuario = cursor.fetchone()

            if usuario and bcrypt.check_password_hash(
                usuario["password_hash"], password
            ):
                session.clear()
                session["id_usuario"] = usuario["id_usuario"]
                session["id_negocio"] = usuario["id_negocio"]
                session["nombre"] = usuario["nombre"]
                session["rol"] = usuario["rol"]

                return redirect(url_for("inicio"))

            flash("Correo o contraseña incorrectos.", "error")

        except Error:
            app.logger.exception("Error al iniciar sesión")
            flash("No se pudo iniciar sesión.", "error")

        finally:
            if cursor is not None:
                cursor.close()
            if conexion is not None and conexion.is_connected():
                conexion.close()

        return redirect(url_for("login"))

    return render_template("login.html")
@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/productos", methods=["GET", "POST"])
def productos():
    if "id_usuario" not in session:
        return redirect(url_for("login"))

    id_negocio = session["id_negocio"]
    conexion = None
    cursor = None

    try:
        conexion = conectar_db()
        cursor = conexion.cursor(dictionary=True)

        if request.method == "POST":
            nombre = request.form.get("nombre", "").strip()
            categoria = request.form.get("categoria", "")
            precio = Decimal(request.form.get("precio", ""))
            stock = int(request.form.get("stock", ""))
            stock_minimo = int(
                request.form.get("stock_minimo", "")
            )

            if (
                not nombre or len(nombre) > 100
                or not precio.is_finite()
                or precio < 0 or precio > Decimal("99999999.99")
                or stock < 0 or stock_minimo < 0
            ):
                raise ValueError("Datos del producto no válidos")

            # Verificar que la categoría pertenece al negocio
            cursor.execute("""
                SELECT id_categoria
                FROM categorias
                WHERE id_categoria = %s AND id_negocio = %s
            """, (categoria, id_negocio))

            if not cursor.fetchone():
                flash("Selecciona una categoría válida.", "error")
                return redirect(url_for("productos"))

            cursor.execute("""
                INSERT INTO productos
                    (id_negocio, nombre, id_categoria,
                     precio, stock, stock_minimo)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                id_negocio, nombre, categoria,
                precio, stock, stock_minimo
            ))

            conexion.commit()
            flash("Producto registrado correctamente.", "success")
            return redirect(url_for("productos"))

        cursor.execute("""
            SELECT id_categoria, nombre
            FROM categorias
            WHERE id_negocio = %s
            ORDER BY nombre
        """, (id_negocio,))
        categorias = cursor.fetchall()

        cursor.execute("""
            SELECT nombre, categoria, precio,
                   stock_disponible, estado_inventario
            FROM v_productos
            WHERE id_negocio = %s AND activo = TRUE
            ORDER BY nombre
        """, (id_negocio,))
        lista_productos = cursor.fetchall()

        return render_template(
            "productos.html",
            nombre_usuario=session["nombre"],
            categorias=categorias,
            lista_productos=lista_productos
        )

    except (ValueError, InvalidOperation):
        flash("Revisa los datos del producto.", "error")
        return redirect(url_for("productos"))

    except Error:
        if conexion:
            conexion.rollback()
        app.logger.exception("Error al consultar o guardar productos")
        flash("Ocurrió un error con la base de datos.", "error")
        return redirect(url_for("inicio"))

    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()


@app.route("/categorias/agregar", methods=["POST"])
def agregar_categoria():
    if "id_usuario" not in session:
        return redirect(url_for("login"))

    nombre = request.form.get("nombre_categoria", "").strip()

    if not nombre or len(nombre) > 50:
        flash("Escribe una categoría válida (máximo 50 caracteres).", "error")
        return redirect(url_for("productos"))

    conexion = None
    cursor = None

    try:
        conexion = conectar_db()
        cursor = conexion.cursor()

        cursor.execute("""
            INSERT INTO categorias (id_negocio, nombre)
            VALUES (%s, %s)
        """, (session["id_negocio"], nombre))

        conexion.commit()
        flash("Categoría agregada correctamente.", "success")

    except Error as error:
        if conexion:
            conexion.rollback()

        if error.errno == 1062:
            flash("Esta categoría ya existe en tu negocio.", "error")
        else:
            app.logger.exception("Error al agregar categoría")
            flash("No se pudo agregar la categoría.", "error")

    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()

    return redirect(url_for("productos"))


@app.route("/inventario")
def inventario():
    if "id_usuario" not in session:
        return redirect(url_for("login"))

    id_negocio = session["id_negocio"]
    conexion = None
    cursor = None

    try:
        conexion = conectar_db()
        cursor = conexion.cursor(dictionary=True)

        cursor.execute("""
            SELECT
    p.id_producto,
    p.nombre,
    c.nombre AS categoria,
                p.precio,
                p.stock,
                p.stock_minimo,
                p.estado_inventario
            FROM productos p
            JOIN categorias c
                ON p.id_categoria = c.id_categoria
                AND p.id_negocio = c.id_negocio
            WHERE p.id_negocio = %s
              AND p.activo = TRUE
            ORDER BY p.nombre
        """, (id_negocio,))

        productos = cursor.fetchall()

        total_productos = len(productos)
        total_unidades = sum(p["stock"] for p in productos)
        stock_bajo = sum(
            1 for p in productos
            if p["estado_inventario"] == "Stock bajo"
        )
        agotados = sum(
            1 for p in productos
            if p["estado_inventario"] == "Agotado"
        )

        return render_template(
            "inventario.html",
            nombre_usuario=session["nombre"],
            productos=productos,
            total_productos=total_productos,
            total_unidades=total_unidades,
            stock_bajo=stock_bajo,
            agotados=agotados
        )

    except Error:
        app.logger.exception("Error al consultar inventario")
        return "No se pudo cargar el inventario.", 500

    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()
            
@app.route("/ventas", methods=["GET", "POST"])
def ventas():
    if "id_usuario" not in session:
        return redirect(url_for("login"))

    id_negocio = session["id_negocio"]
    id_usuario = session["id_usuario"]
    conexion = None
    cursor = None

    try:
        conexion = conectar_db()
        cursor = conexion.cursor(dictionary=True)

        if request.method == "POST":
            try:
                id_producto = int(request.form.get("producto", ""))
                cantidad = int(request.form.get("cantidad", ""))
                id_metodo = int(request.form.get("metodo_pago", ""))
            except (ValueError, TypeError):
                flash("Ingresa datos válidos.", "error")
                return redirect(url_for("ventas"))

            if cantidad <= 0:
                flash("La cantidad debe ser mayor que cero.", "error")
                return redirect(url_for("ventas"))

            # El procedimiento valida stock y calcula importe.
            # El trigger de MySQL descuenta las existencias.
            cursor.callproc("sp_registrar_venta", [
                id_negocio,
                id_usuario,
                id_producto,
                cantidad,
                id_metodo,
                None
            ])

            conexion.commit()
            flash("Venta registrada correctamente.", "success")
            return redirect(url_for("ventas"))

        cursor.execute("""
            SELECT id_producto, nombre, precio, stock
            FROM productos
            WHERE id_negocio = %s
              AND activo = TRUE
              AND stock > 0
            ORDER BY nombre
        """, (id_negocio,))
        productos = cursor.fetchall()

        cursor.execute("""
            SELECT id_metodo_pago, nombre
            FROM metodos_pago
            ORDER BY nombre
        """)
        metodos = cursor.fetchall()

        cursor.execute("""
            SELECT producto, cantidad, metodo_pago,
                   importe_total, fecha_registro
            FROM v_ventas
            WHERE id_negocio = %s
            ORDER BY fecha_registro DESC
        """, (id_negocio,))
        historial = cursor.fetchall()

        return render_template(
            "ventas.html",
            nombre_usuario=session["nombre"],
            productos=productos,
            metodos=metodos,
            historial=historial
        )

    except Error as error:
        if conexion is not None:
            conexion.rollback()

        if getattr(error, "sqlstate", None) == "45000":
            flash(str(error), "error")
        else:
            app.logger.exception("Error al registrar o consultar ventas")
            flash("No se pudo realizar la operación.", "error")

        return redirect(url_for("inicio"))

    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()


@app.route("/inventario/reabastecer", methods=["POST"])
def reabastecer():
    if "id_usuario" not in session:
        return redirect(url_for("login"))

    try:
        id_producto = int(request.form.get("id_producto", ""))
        cantidad = int(request.form.get("cantidad", ""))
    except (ValueError, TypeError):
        flash("Introduce una cantidad válida.", "error")
        return redirect(url_for("inventario"))

    if cantidad <= 0:
        flash("La cantidad debe ser mayor que cero.", "error")
        return redirect(url_for("inventario"))

    conexion = None
    cursor = None

    try:
        conexion = conectar_db()
        cursor = conexion.cursor()

        cursor.execute("""
            UPDATE productos
            SET stock = stock + %s
            WHERE id_producto = %s
              AND id_negocio = %s
              AND activo = TRUE
        """, (cantidad, id_producto, session["id_negocio"]))

        if cursor.rowcount != 1:
            conexion.rollback()
            flash("Producto no encontrado.", "error")
        else:
            conexion.commit()
            flash("Inventario actualizado correctamente.", "success")

    except Error:
        if conexion is not None:
            conexion.rollback()
        app.logger.exception("Error al reabastecer inventario")
        flash("No se pudo actualizar el inventario.", "error")

    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()

    return redirect(url_for("inventario"))



@app.route("/clientes", methods=["GET", "POST"])
def clientes():
    if "id_usuario" not in session:
        return redirect(url_for("login"))

    id_negocio = session["id_negocio"]
    conexion = None
    cursor = None

    try:
        conexion = conectar_db()
        cursor = conexion.cursor(dictionary=True)

        if request.method == "POST":
            nombre = request.form.get("nombre", "").strip()
            if not nombre or len(nombre) > 100:
                flash("Escribe un nombre válido (máximo 100 caracteres).", "error")
                return redirect(url_for("clientes"))

            cursor.execute("""
                INSERT INTO clientes (id_negocio, nombre)
                VALUES (%s, %s)
            """, (id_negocio, nombre))
            conexion.commit()
            flash("Cliente registrado correctamente.", "success")
            return redirect(url_for("clientes"))

        cursor.execute("""
            SELECT id_cliente, nombre, pedidos_asociados
            FROM v_clientes
            WHERE id_negocio = %s
            ORDER BY nombre, id_cliente
        """, (id_negocio,))
        lista_clientes = cursor.fetchall()

        return render_template(
            "clientes.html",
            nombre_usuario=session["nombre"],
            lista_clientes=lista_clientes
        )

    except Error:
        if conexion is not None:
            conexion.rollback()
        app.logger.exception("Error al consultar o registrar clientes")
        flash("No se pudo completar la operación con MySQL.", "error")
        return redirect(url_for("inicio"))

    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()



# PEDIDOS: el pedido y su estado de pago no generan ventas ni descuentan stock.
@app.route("/pedidos", methods=["GET", "POST"])
def pedidos():
    if "id_usuario" not in session:
        return redirect(url_for("login"))

    id_negocio = session["id_negocio"]
    conexion = None
    cursor = None
    try:
        conexion = conectar_db()
        cursor = conexion.cursor(dictionary=True)

        if request.method == "POST":
            try:
                id_cliente = int(request.form.get("id_cliente", ""))
            except (ValueError, TypeError):
                flash("Selecciona un cliente válido.", "error")
                return redirect(url_for("pedidos"))

            cursor.execute("""
                SELECT id_cliente FROM clientes
                WHERE id_cliente = %s AND id_negocio = %s
            """, (id_cliente, id_negocio))
            if cursor.fetchone() is None:
                flash("El cliente no pertenece a tu negocio.", "error")
                return redirect(url_for("pedidos"))

            cursor.callproc("sp_crear_pedido", [
                id_negocio, session["id_usuario"], id_cliente
            ])
            conexion.commit()
            flash("Pedido creado. Ahora puedes agregarle productos.", "success")
            return redirect(url_for("pedidos"))

        cursor.execute("""
            SELECT id_cliente, nombre FROM clientes
            WHERE id_negocio = %s ORDER BY nombre
        """, (id_negocio,))
        lista_clientes = cursor.fetchall()

        cursor.execute("""
            SELECT id_producto, nombre, precio, stock FROM productos
            WHERE id_negocio = %s AND activo = TRUE
            ORDER BY nombre
        """, (id_negocio,))
        lista_productos = cursor.fetchall()

        cursor.execute("""
            SELECT id_pedido, numero_pedido, cliente, productos,
                   total, estado_pago, fecha_pedido
            FROM v_pedidos WHERE id_negocio = %s
            ORDER BY fecha_pedido DESC, id_pedido DESC
        """, (id_negocio,))
        lista_pedidos = cursor.fetchall()

        cursor.execute("""
            SELECT d.id_pedido, p.nombre, d.cantidad,
                   d.precio_unitario,
                   d.cantidad * d.precio_unitario AS subtotal
            FROM detalle_pedido d
            JOIN pedidos pe ON pe.id_pedido = d.id_pedido
                          AND pe.id_negocio = d.id_negocio
            JOIN productos p ON p.id_producto = d.id_producto
                            AND p.id_negocio = d.id_negocio
            WHERE d.id_negocio = %s
            ORDER BY d.id_pedido DESC, p.nombre
        """, (id_negocio,))
        detalles = {}
        for item in cursor.fetchall():
            detalles.setdefault(item["id_pedido"], []).append(item)

        return render_template(
            "pedidos.html", nombre_usuario=session["nombre"],
            lista_clientes=lista_clientes,
            lista_productos=lista_productos,
            lista_pedidos=lista_pedidos, detalles=detalles
        )
    except Error:
        if conexion is not None:
            conexion.rollback()
        app.logger.exception("Error en la sección de pedidos")
        flash("No se pudo completar la operación de pedidos.", "error")
        return redirect(url_for("inicio"))
    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()


@app.route("/pedidos/agregar-producto", methods=["POST"])
def agregar_producto_pedido():
    if "id_usuario" not in session:
        return redirect(url_for("login"))
    try:
        id_pedido = int(request.form.get("id_pedido", ""))
        id_producto = int(request.form.get("id_producto", ""))
        cantidad = int(request.form.get("cantidad", ""))
        if cantidad <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        flash("Selecciona un pedido, producto y cantidad válidos.", "error")
        return redirect(url_for("pedidos"))

    id_negocio = session["id_negocio"]
    conexion = None
    cursor = None
    try:
        conexion = conectar_db()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT estado_pago FROM pedidos
            WHERE id_pedido = %s AND id_negocio = %s
            FOR UPDATE
        """, (id_pedido, id_negocio))
        pedido = cursor.fetchone()
        if pedido is None or pedido["estado_pago"] != "Pendiente":
            conexion.rollback()
            flash("Solo puedes agregar productos a pedidos pendientes de tu negocio.", "error")
            return redirect(url_for("pedidos"))

        cursor.execute("""
            SELECT id_producto FROM productos
            WHERE id_producto = %s AND id_negocio = %s AND activo = TRUE
        """, (id_producto, id_negocio))
        if cursor.fetchone() is None:
            conexion.rollback()
            flash("El producto no está disponible en tu negocio.", "error")
            return redirect(url_for("pedidos"))

        cursor.callproc("sp_agregar_item_pedido", [
            id_negocio, id_pedido, id_producto, cantidad
        ])
        conexion.commit()
        flash("Producto agregado al pedido y total actualizado.", "success")
    except Error:
        if conexion is not None:
            conexion.rollback()
        app.logger.exception("Error al agregar producto al pedido")
        flash("No se pudo agregar el producto al pedido.", "error")
    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()
    return redirect(url_for("pedidos"))


@app.route("/pedidos/estado", methods=["POST"])
def actualizar_estado_pedido():
    if "id_usuario" not in session:
        return redirect(url_for("login"))
    try:
        id_pedido = int(request.form.get("id_pedido", ""))
    except (TypeError, ValueError):
        flash("Pedido inválido.", "error")
        return redirect(url_for("pedidos"))
    estado = request.form.get("estado_pago", "")
    if estado not in ("Pendiente", "Pagado", "Cancelado"):
        flash("Estado de pago inválido.", "error")
        return redirect(url_for("pedidos"))

    conexion = None
    cursor = None
    try:
        conexion = conectar_db()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("""
            SELECT estado_pago,
                (SELECT COUNT(*) FROM detalle_pedido d
                 WHERE d.id_pedido = p.id_pedido AND d.id_negocio = p.id_negocio)
                AS articulos
            FROM pedidos p
            WHERE p.id_pedido = %s AND p.id_negocio = %s FOR UPDATE
        """, (id_pedido, session["id_negocio"]))
        pedido = cursor.fetchone()
        if pedido is None:
            flash("Pedido no encontrado.", "error")
        elif pedido["estado_pago"] != "Pendiente":
            flash("Solo puedes cambiar el estado de pedidos pendientes.", "error")
        elif estado == "Pagado" and pedido["articulos"] == 0:
            flash("Agrega productos antes de marcar el pedido como pagado.", "error")
        else:
            cursor.execute("""
                UPDATE pedidos SET estado_pago = %s
                WHERE id_pedido = %s AND id_negocio = %s
            """, (estado, id_pedido, session["id_negocio"]))
            conexion.commit()
            flash("Estado del pedido actualizado.", "success")
    except Error:
        if conexion is not None:
            conexion.rollback()
        app.logger.exception("Error al actualizar estado de pedido")
        flash("No se pudo actualizar el estado del pedido.", "error")
    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()
    return redirect(url_for("pedidos"))




# ESTADÍSTICAS: proyecciones simples a partir de ventas reales.
@app.route("/estadisticas", methods=["GET", "POST"])
def estadisticas():
    if "id_usuario" not in session:
        return redirect(url_for("login"))

    negocio = session["id_negocio"]
    conexion = None
    cursor = None
    try:
        conexion = conectar_db()
        cursor = conexion.cursor(dictionary=True)

        # El costo solo puede editarlo el administrador de su propio negocio.
        if request.method == "POST":
            if session.get("rol") != "administrador":
                flash("Solo el administrador puede modificar los costos.", "error")
                return redirect(url_for("estadisticas"))
            try:
                producto = int(request.form.get("id_producto", ""))
                costo = Decimal(request.form.get("costo_compra", ""))
                if (producto <= 0 or not costo.is_finite() or costo < 0
                        or costo > Decimal("99999999.99")
                        or costo.as_tuple().exponent < -2):
                    raise ValueError()
            except (ValueError, InvalidOperation, TypeError):
                flash("Indica un costo válido con máximo dos decimales.", "error")
                return redirect(url_for("estadisticas"))
            cursor.execute("""
                UPDATE productos SET costo_compra = %s
                WHERE id_producto = %s AND id_negocio = %s AND activo = TRUE
            """, (costo, producto, negocio))
            if cursor.rowcount == 0:
                # rowcount puede ser 0 si el costo no cambió; revisar la pertenencia.
                cursor.execute("""
                    SELECT id_producto FROM productos
                    WHERE id_producto = %s AND id_negocio = %s AND activo = TRUE
                """, (producto, negocio))
                if cursor.fetchone() is None:
                    conexion.rollback()
                    flash("Producto no encontrado en tu negocio.", "error")
                    return redirect(url_for("estadisticas"))
            conexion.commit()
            flash("Costo de compra guardado correctamente.", "success")
            return redirect(url_for("estadisticas"))

        cursor.execute("""
            SELECT id_producto, nombre, precio, costo_compra
            FROM productos WHERE id_negocio = %s AND activo = TRUE
            ORDER BY nombre
        """, (negocio,))
        productos_costos = cursor.fetchall()

        cursor.execute("""
            SELECT COALESCE(SUM(v.importe_total), 0) AS ingresos,
                   COUNT(*) AS operaciones,
                   COALESCE(SUM(v.cantidad), 0) AS unidades,
                   SUM(CASE WHEN p.costo_compra IS NULL THEN 1 ELSE 0 END)
                       AS ventas_sin_costo,
                   COALESCE(SUM(CASE WHEN p.costo_compra IS NOT NULL
                       THEN v.importe_total - v.cantidad * p.costo_compra
                       ELSE 0 END), 0) AS margen_estimado
            FROM ventas v
            JOIN productos p ON p.id_producto = v.id_producto
                            AND p.id_negocio = v.id_negocio
            WHERE v.id_negocio = %s
              AND v.fecha_registro >= CURDATE() - INTERVAL 29 DAY
              AND v.fecha_registro < CURDATE() + INTERVAL 1 DAY
        """, (negocio,))
        resumen = cursor.fetchone()
        ingresos = Decimal(str(resumen["ingresos"]))
        margen = Decimal(str(resumen["margen_estimado"]))
        operaciones = resumen["operaciones"]
        sin_costo = resumen["ventas_sin_costo"] or 0
        # Los costos actuales permiten estimar margen bruto, no utilidad neta.
        margen_disponible = operaciones > 0 and sin_costo == 0
        ticket_promedio = (ingresos / operaciones).quantize(Decimal("0.01")) if operaciones else Decimal("0")
        promedio_diario = ingresos / Decimal("30")
        proyeccion_7 = (promedio_diario * 7).quantize(Decimal("0.01")) if operaciones else None
        proyeccion_30 = (promedio_diario * 30).quantize(Decimal("0.01")) if operaciones else None
        margen_proyectado_30 = (margen / Decimal("30") * 30).quantize(Decimal("0.01")) if margen_disponible else None

        cursor.execute("""
            SELECT DATE(fecha_registro) AS fecha, SUM(importe_total) AS ingresos
            FROM ventas
            WHERE id_negocio = %s
              AND fecha_registro >= CURDATE() - INTERVAL 6 DAY
              AND fecha_registro < CURDATE() + INTERVAL 1 DAY
            GROUP BY DATE(fecha_registro)
            ORDER BY fecha
        """, (negocio,))
        serie = {r["fecha"]: Decimal(str(r["ingresos"])) for r in cursor.fetchall()}
        from datetime import date, timedelta
        dias = [date.today() - timedelta(days=n) for n in range(6, -1, -1)]
        max_ingreso = max([serie.get(d, Decimal("0")) for d in dias] + [Decimal("1")])
        grafica = [{"fecha": d.strftime("%d/%m"),
                    "ingresos": serie.get(d, Decimal("0")),
                    "altura": round(float(serie.get(d, Decimal("0")) / max_ingreso * 100), 1)}
                   for d in dias]

        cursor.execute("""
            SELECT p.nombre, SUM(v.cantidad) AS unidades,
                   SUM(v.importe_total) AS ingresos
            FROM ventas v
            JOIN productos p ON p.id_producto = v.id_producto
                            AND p.id_negocio = v.id_negocio
            WHERE v.id_negocio = %s
            GROUP BY p.id_producto, p.nombre
            ORDER BY unidades DESC, ingresos DESC
            LIMIT 5
        """, (negocio,))
        mas_vendidos = cursor.fetchall()

        return render_template(
            "estadisticas.html", nombre_usuario=session["nombre"],
            rol=session.get("rol"), productos_costos=productos_costos,
            ingresos=ingresos, operaciones=operaciones,
            unidades=resumen["unidades"], ticket_promedio=ticket_promedio,
            margen=margen if margen_disponible else None,
            sin_costo=sin_costo, proyeccion_7=proyeccion_7,
            proyeccion_30=proyeccion_30, margen_proyectado_30=margen_proyectado_30,
            grafica=grafica, mas_vendidos=mas_vendidos
        )
    except Error:
        if conexion is not None:
            conexion.rollback()
        app.logger.exception("Error en estadísticas")
        flash("No se pudieron cargar las estadísticas. Revisa que hayas ejecutado la actualización SQL.", "error")
        return redirect(url_for("inicio"))
    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()


if __name__ == "__main__":
    app.run(debug=True)

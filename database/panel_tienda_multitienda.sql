-- =====================================================
-- Panel de gestión de tienda: versión MULTI-TIENDA (MySQL 8+)
-- Cada cliente (dueño de negocio) se registra desde la página web,
-- crea su propia tienda y carga sus propios productos.
-- La base arranca VACÍA (solo los métodos de pago).
--
-- Nota: "clientes" = compradores de cada tienda.
--       "negocios/usuarios" = quienes usan la página web.
-- =====================================================
DROP DATABASE IF EXISTS panel_tienda;
CREATE DATABASE panel_tienda CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE panel_tienda;

-- ---------- TABLAS ----------

-- Negocio / Tienda (un registro por cada cliente de la plataforma)
CREATE TABLE negocios (
    id_negocio        INT AUTO_INCREMENT PRIMARY KEY,
    nombre_comercial  VARCHAR(100) NOT NULL,
    espacio_trabajo   VARCHAR(100) NOT NULL UNIQUE,
    siguiente_pedido  INT NOT NULL DEFAULT 1,           -- contador de PED-0001, PED-0002...
    fecha_registro    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Usuario (quien inicia sesión en la página web)
CREATE TABLE usuarios (
    id_usuario     INT AUTO_INCREMENT PRIMARY KEY,
    id_negocio     INT NOT NULL,
    nombre         VARCHAR(100) NOT NULL,
    iniciales      VARCHAR(3) AS (UPPER(CONCAT(
                       LEFT(nombre, 1),
                       IF(LOCATE(' ', nombre) > 0, LEFT(SUBSTRING_INDEX(nombre, ' ', -1), 1), '')
                   ))) VIRTUAL,
    avatar_url     VARCHAR(255),
    correo         VARCHAR(100) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,               -- guardar SIEMPRE cifrada (bcrypt/argon2), nunca en texto plano
    rol            ENUM('administrador','vendedor') NOT NULL DEFAULT 'administrador',
    activo         BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id_usuario, id_negocio),
    FOREIGN KEY (id_negocio) REFERENCES negocios(id_negocio)
);

-- Categorías propias de cada negocio
CREATE TABLE categorias (
    id_categoria INT AUTO_INCREMENT PRIMARY KEY,
    id_negocio   INT NOT NULL,
    nombre       VARCHAR(50) NOT NULL,
    UNIQUE (id_negocio, nombre),
    UNIQUE (id_categoria, id_negocio),
    FOREIGN KEY (id_negocio) REFERENCES negocios(id_negocio)
);

-- Producto + Inventario (los captura el cliente)
CREATE TABLE productos (
    id_producto        INT AUTO_INCREMENT PRIMARY KEY,
    id_negocio         INT NOT NULL,
    nombre             VARCHAR(100) NOT NULL,
    id_categoria       INT NOT NULL,
    precio             DECIMAL(10,2) NOT NULL CHECK (precio >= 0),
    stock              INT NOT NULL DEFAULT 0 CHECK (stock >= 0),
    stock_minimo       INT NOT NULL DEFAULT 10,
    activo             BOOLEAN NOT NULL DEFAULT TRUE,
    estado_inventario  VARCHAR(12) AS (
                          CASE WHEN stock = 0 THEN 'Agotado'
                               WHEN stock <= stock_minimo THEN 'Stock bajo'
                               ELSE 'Disponible' END
                       ) VIRTUAL,
    UNIQUE (id_negocio, nombre),
    UNIQUE (id_producto, id_negocio),
    FOREIGN KEY (id_negocio) REFERENCES negocios(id_negocio),
    -- la categoría debe pertenecer al mismo negocio
    FOREIGN KEY (id_categoria, id_negocio) REFERENCES categorias(id_categoria, id_negocio)
);

-- Clientes (compradores) de cada tienda
CREATE TABLE clientes (
    id_cliente  INT AUTO_INCREMENT PRIMARY KEY,
    id_negocio  INT NOT NULL,
    nombre      VARCHAR(100) NOT NULL,
    iniciales   VARCHAR(3) AS (UPPER(CONCAT(
                    LEFT(nombre, 1),
                    IF(LOCATE(' ', nombre) > 0, LEFT(SUBSTRING_INDEX(nombre, ' ', -1), 1), '')
                ))) VIRTUAL,
    avatar_url  VARCHAR(255),
    UNIQUE (id_cliente, id_negocio),
    FOREIGN KEY (id_negocio) REFERENCES negocios(id_negocio)
);

-- Método de pago (catálogo común)
CREATE TABLE metodos_pago (
    id_metodo_pago INT AUTO_INCREMENT PRIMARY KEY,
    nombre         VARCHAR(30) NOT NULL UNIQUE
);

-- Venta (cliente opcional; la registra un usuario del negocio)
CREATE TABLE ventas (
    id_venta         INT AUTO_INCREMENT PRIMARY KEY,
    id_negocio       INT NOT NULL,
    id_usuario       INT NOT NULL,
    id_producto      INT NOT NULL,
    cantidad         INT NOT NULL CHECK (cantidad > 0),
    id_metodo_pago   INT NOT NULL,
    id_cliente       INT NULL,
    importe_total    DECIMAL(10,2) NOT NULL CHECK (importe_total >= 0),
    fecha_registro   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_usuario, id_negocio)  REFERENCES usuarios(id_usuario, id_negocio),
    FOREIGN KEY (id_producto, id_negocio) REFERENCES productos(id_producto, id_negocio),
    FOREIGN KEY (id_cliente, id_negocio)  REFERENCES clientes(id_cliente, id_negocio),
    FOREIGN KEY (id_metodo_pago) REFERENCES metodos_pago(id_metodo_pago)
);

-- Pedido
CREATE TABLE pedidos (
    id_pedido      INT AUTO_INCREMENT PRIMARY KEY,
    id_negocio     INT NOT NULL,
    numero_pedido  VARCHAR(20) NOT NULL,
    id_usuario     INT NOT NULL,
    id_cliente     INT NOT NULL,
    total          DECIMAL(10,2) NOT NULL DEFAULT 0,
    estado_pago    ENUM('Pendiente','Pagado','Cancelado') NOT NULL DEFAULT 'Pendiente',
    fecha_pedido   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id_negocio, numero_pedido),
    UNIQUE (id_pedido, id_negocio),
    FOREIGN KEY (id_usuario, id_negocio) REFERENCES usuarios(id_usuario, id_negocio),
    FOREIGN KEY (id_cliente, id_negocio) REFERENCES clientes(id_cliente, id_negocio)
);

CREATE TABLE detalle_pedido (
    id_pedido       INT NOT NULL,
    id_negocio      INT NOT NULL,
    id_producto     INT NOT NULL,
    cantidad        INT NOT NULL CHECK (cantidad > 0),
    precio_unitario DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (id_pedido, id_producto),
    FOREIGN KEY (id_pedido, id_negocio)   REFERENCES pedidos(id_pedido, id_negocio),
    FOREIGN KEY (id_producto, id_negocio) REFERENCES productos(id_producto, id_negocio)
);

CREATE INDEX idx_ventas_fecha  ON ventas (id_negocio, fecha_registro);
CREATE INDEX idx_pedidos_fecha ON pedidos (id_negocio, fecha_pedido);

-- ---------- ÚNICOS DATOS INICIALES: MÉTODOS DE PAGO ----------
INSERT INTO metodos_pago (nombre) VALUES ('Efectivo'), ('Transferencia');

-- ---------- TRIGGER: descuenta el stock al registrar una venta ----------
DELIMITER //
CREATE TRIGGER trg_venta_descuenta_stock
AFTER INSERT ON ventas
FOR EACH ROW
BEGIN
    UPDATE productos SET stock = GREATEST(stock - NEW.cantidad, 0)
    WHERE id_producto = NEW.id_producto AND id_negocio = NEW.id_negocio;
END//
DELIMITER ;

-- ---------- VISTAS (en la web siempre filtrar con WHERE id_negocio = ?) ----------

-- Productos: categoría, precio, stock, número de ventas y estado de inventario
CREATE VIEW v_productos AS
SELECT p.id_producto, p.id_negocio, p.nombre, c.nombre AS categoria, p.precio,
       p.stock AS stock_disponible, p.activo,
       COALESCE(SUM(v.cantidad), 0) AS numero_ventas,
       p.estado_inventario
FROM productos p
JOIN categorias c ON c.id_categoria = p.id_categoria
LEFT JOIN ventas v ON v.id_producto = p.id_producto
GROUP BY p.id_producto, p.id_negocio, p.nombre, c.nombre, p.precio, p.stock, p.activo, p.estado_inventario;

-- Inventario: productos activos y alertas de stock bajo
CREATE VIEW v_inventario_resumen AS
SELECT id_negocio,
       SUM(activo) AS productos_activos,
       SUM(stock <= stock_minimo AND activo) AS alertas_stock_bajo
FROM productos
GROUP BY id_negocio;

CREATE VIEW v_alertas_stock AS
SELECT id_negocio, nombre AS producto, stock AS cantidad_disponible, stock_minimo, estado_inventario
FROM productos
WHERE activo AND stock <= stock_minimo;

-- Pedidos: cliente, productos, total, estado y tiempo transcurrido
CREATE VIEW v_pedidos AS
SELECT pe.id_pedido, pe.numero_pedido, pe.id_negocio, cl.nombre AS cliente, cl.iniciales,
       GROUP_CONCAT(pr.nombre SEPARATOR ', ') AS productos,
       pe.total, pe.estado_pago, pe.fecha_pedido,
       TIMESTAMPDIFF(MINUTE, pe.fecha_pedido, NOW()) AS minutos_transcurridos
FROM pedidos pe
JOIN clientes cl ON cl.id_cliente = pe.id_cliente
LEFT JOIN detalle_pedido d ON d.id_pedido = pe.id_pedido
LEFT JOIN productos pr ON pr.id_producto = d.id_producto
GROUP BY pe.id_pedido, pe.numero_pedido, pe.id_negocio, cl.nombre, cl.iniciales,
         pe.total, pe.estado_pago, pe.fecha_pedido;

-- Clientes con pedidos asociados
CREATE VIEW v_clientes AS
SELECT cl.id_cliente, cl.id_negocio, cl.nombre, cl.iniciales, cl.avatar_url,
       COUNT(pe.id_pedido) AS pedidos_asociados
FROM clientes cl
LEFT JOIN pedidos pe ON pe.id_cliente = cl.id_cliente
GROUP BY cl.id_cliente, cl.id_negocio, cl.nombre, cl.iniciales, cl.avatar_url;

-- Ventas con detalle
CREATE VIEW v_ventas AS
SELECT v.id_venta, v.id_negocio, p.nombre AS producto, v.cantidad,
       mp.nombre AS metodo_pago, cl.nombre AS cliente, v.importe_total, v.fecha_registro
FROM ventas v
JOIN productos p      ON p.id_producto = v.id_producto
JOIN metodos_pago mp  ON mp.id_metodo_pago = v.id_metodo_pago
LEFT JOIN clientes cl ON cl.id_cliente = v.id_cliente;

-- Ingresos por día (gráficas de ingresos por periodo)
CREATE VIEW v_ingresos_diarios AS
SELECT id_negocio, DATE(fecha_registro) AS fecha, SUM(importe_total) AS ingresos
FROM ventas
GROUP BY id_negocio, DATE(fecha_registro);

-- ---------- PROCEDIMIENTOS PARA LA PÁGINA WEB ----------

DELIMITER //

-- 1) Registro: crea el negocio y su usuario administrador.
--    La contraseña debe llegar ya cifrada desde la aplicación.
CREATE PROCEDURE sp_registrar_negocio(
    IN p_nombre_comercial VARCHAR(100),
    IN p_espacio_trabajo  VARCHAR(100),
    IN p_nombre           VARCHAR(100),
    IN p_correo           VARCHAR(100),
    IN p_password_hash    VARCHAR(255))
BEGIN
    DECLARE v_negocio INT;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;

    START TRANSACTION;
    INSERT INTO negocios (nombre_comercial, espacio_trabajo)
    VALUES (p_nombre_comercial, p_espacio_trabajo);
    SET v_negocio = LAST_INSERT_ID();

    INSERT INTO usuarios (id_negocio, nombre, correo, password_hash, rol)
    VALUES (v_negocio, p_nombre, p_correo, p_password_hash, 'administrador');
    COMMIT;

    SELECT v_negocio AS id_negocio, LAST_INSERT_ID() AS id_usuario;
END//

-- 2) Venta: valida producto y stock, calcula el importe (el trigger descuenta el stock).
CREATE PROCEDURE sp_registrar_venta(
    IN p_negocio     INT,
    IN p_usuario     INT,
    IN p_producto    INT,
    IN p_cantidad    INT,
    IN p_metodo_pago INT,
    IN p_cliente     INT)          -- NULL si la venta no tiene cliente
BEGIN
    DECLARE v_precio DECIMAL(10,2) DEFAULT NULL;
    DECLARE v_stock  INT DEFAULT NULL;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;

    START TRANSACTION;
    SELECT precio, stock INTO v_precio, v_stock
    FROM productos
    WHERE id_producto = p_producto AND id_negocio = p_negocio AND activo
    FOR UPDATE;

    IF v_precio IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Producto no encontrado o inactivo';
    END IF;
    IF v_stock < p_cantidad THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Stock insuficiente';
    END IF;

    INSERT INTO ventas (id_negocio, id_usuario, id_producto, cantidad, id_metodo_pago, id_cliente, importe_total)
    VALUES (p_negocio, p_usuario, p_producto, p_cantidad, p_metodo_pago, p_cliente, v_precio * p_cantidad);
    COMMIT;

    SELECT LAST_INSERT_ID() AS id_venta, v_precio * p_cantidad AS importe_total;
END//

-- 3) Pedido: crea el encabezado con su número consecutivo (PED-0001, ...).
CREATE PROCEDURE sp_crear_pedido(
    IN p_negocio INT,
    IN p_usuario INT,
    IN p_cliente INT)
BEGIN
    DECLARE v_num INT;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;

    START TRANSACTION;
    UPDATE negocios SET siguiente_pedido = LAST_INSERT_ID(siguiente_pedido) + 1
    WHERE id_negocio = p_negocio;
    SET v_num = LAST_INSERT_ID();

    INSERT INTO pedidos (id_negocio, numero_pedido, id_usuario, id_cliente)
    VALUES (p_negocio, CONCAT('PED-', LPAD(v_num, 4, '0')), p_usuario, p_cliente);
    COMMIT;

    SELECT LAST_INSERT_ID() AS id_pedido, CONCAT('PED-', LPAD(v_num, 4, '0')) AS numero_pedido;
END//

-- 4) Agrega un producto al pedido y recalcula el total.
CREATE PROCEDURE sp_agregar_item_pedido(
    IN p_negocio  INT,
    IN p_pedido   INT,
    IN p_producto INT,
    IN p_cantidad INT)
BEGIN
    DECLARE v_precio DECIMAL(10,2) DEFAULT NULL;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;

    START TRANSACTION;
    SELECT precio INTO v_precio
    FROM productos
    WHERE id_producto = p_producto AND id_negocio = p_negocio AND activo;

    IF v_precio IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Producto no encontrado o inactivo';
    END IF;

    INSERT INTO detalle_pedido (id_pedido, id_negocio, id_producto, cantidad, precio_unitario)
    VALUES (p_pedido, p_negocio, p_producto, p_cantidad, v_precio)
    ON DUPLICATE KEY UPDATE cantidad = cantidad + VALUES(cantidad);

    UPDATE pedidos
    SET total = (SELECT SUM(cantidad * precio_unitario) FROM detalle_pedido WHERE id_pedido = p_pedido)
    WHERE id_pedido = p_pedido AND id_negocio = p_negocio;
    COMMIT;
END//

-- 5) Métricas financieras: '7dias' (últimos 7 días) o 'anio' (año actual),
--    comparadas con el periodo anterior.
CREATE PROCEDURE sp_metricas(IN p_negocio INT, IN p_periodo VARCHAR(10))
BEGIN
    DECLARE v_fin      DATETIME DEFAULT NOW();
    DECLARE v_ini      DATETIME;
    DECLARE v_ini_ant  DATETIME;

    IF p_periodo = '7dias' THEN
        SET v_ini     = v_fin - INTERVAL 7 DAY;
        SET v_ini_ant = v_ini - INTERVAL 7 DAY;
    ELSE
        SET v_ini     = MAKEDATE(YEAR(v_fin), 1);
        SET v_ini_ant = v_ini - INTERVAL 1 YEAR;
    END IF;

    SELECT
        a.ventas_totales,
        (SELECT COUNT(*) FROM pedidos
          WHERE id_negocio = p_negocio
            AND fecha_pedido >= v_ini AND fecha_pedido < v_fin) AS numero_pedidos,
        a.ticket_promedio,
        b.ventas_totales AS ventas_periodo_anterior,
        ROUND((a.ventas_totales - b.ventas_totales)
              / NULLIF(b.ventas_totales, 0) * 100, 2) AS variacion_porcentual
    FROM (SELECT COALESCE(SUM(importe_total), 0) AS ventas_totales,
                 COALESCE(ROUND(AVG(importe_total), 2), 0) AS ticket_promedio
          FROM ventas
          WHERE id_negocio = p_negocio
            AND fecha_registro >= v_ini AND fecha_registro < v_fin) a,
         (SELECT COALESCE(SUM(importe_total), 0) AS ventas_totales
          FROM ventas
          WHERE id_negocio = p_negocio
            AND fecha_registro >= v_ini_ant AND fecha_registro < v_ini) b;
END//

DELIMITER ;

-- ---------- EJEMPLO DE FLUJO (descomenta para probar) ----------
-- CALL sp_registrar_negocio('Mi Papelería', 'mi-papeleria', 'Ana López', 'ana@correo.com', '$2b$12$hashDeEjemplo');
-- INSERT INTO categorias (id_negocio, nombre) VALUES (1, 'Cuadernos');
-- INSERT INTO productos (id_negocio, nombre, id_categoria, precio, stock, stock_minimo)
--        VALUES (1, 'Cuaderno profesional', 1, 32.00, 100, 20);
-- INSERT INTO clientes (id_negocio, nombre) VALUES (1, 'María González');
-- CALL sp_registrar_venta(1, 1, 1, 3, 1, 1);
-- CALL sp_crear_pedido(1, 1, 1);
-- CALL sp_agregar_item_pedido(1, 1, 1, 2);
-- CALL sp_metricas(1, '7dias');

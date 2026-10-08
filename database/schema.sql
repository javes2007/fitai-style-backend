-- ============================================================
-- FitAI Style - BASE DE DATOS UNICA
-- MySQL 8.x / utf8mb4
--
-- Este es el UNICO esquema que debe utilizar el proyecto.
-- No necesita archivos de migracion para una instalacion nueva.
--
-- Para una instalacion NUEVA:
--   1. Ejecutar este archivo completo.
--   2. Configurar DB_NAME=fitai_style en el backend.
--
-- IMPORTANTE:
-- Este archivo esta pensado para crear una base limpia.
-- No elimina datos existentes automaticamente.
-- ============================================================

CREATE DATABASE IF NOT EXISTS fitai_style
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE fitai_style;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================
-- 1. USUARIOS
-- ============================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(190) NOT NULL,
    contrasena VARCHAR(255) NOT NULL,

    -- Integracion opcional con Firebase.
    firebase_uid VARCHAR(128) NULL,

    fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    -- Perfil corporal
    altura DECIMAL(6,2) NULL,
    peso DECIMAL(6,2) NULL,
    tipo_cuerpo VARCHAR(50) NULL,
    genero VARCHAR(30) NULL,
    ancho_hombros DECIMAL(6,2) NULL,
    pecho DECIMAL(6,2) NULL,
    cintura DECIMAL(6,2) NULL,
    cadera DECIMAL(6,2) NULL,

    activo TINYINT(1) NOT NULL DEFAULT 1,

    UNIQUE KEY uq_usuarios_email (email),
    UNIQUE KEY uq_usuarios_firebase_uid (firebase_uid),
    INDEX idx_usuarios_nombre (nombre)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 2. FOTOS DEL USUARIO
-- ============================================================

CREATE TABLE IF NOT EXISTS fotos_usuario (
    id_foto INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT UNSIGNED NOT NULL,
    url_imagen VARCHAR(500) NOT NULL,
    tipo VARCHAR(30) NULL,
    foto_principal TINYINT(1) NOT NULL DEFAULT 0,
    fecha_subida TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_fotos_usuario (id_usuario),
    CONSTRAINT fk_fotos_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuarios(id_usuario)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 3. PERFIL Y CONFIGURACION DEL AVATAR
-- ============================================================

CREATE TABLE IF NOT EXISTS avatar_perfiles (
    id_avatar INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT UNSIGNED NOT NULL,

    edad TINYINT UNSIGNED NULL,
    estilo VARCHAR(50) NULL,

    -- Configuracion usada por el editor 3D.
    cuerpo JSON NULL,
    rostro JSON NULL,
    cabello JSON NULL,
    estetica JSON NULL,

    foto_analizada TINYINT(1) NOT NULL DEFAULT 0,

    -- ADN/configuracion completa del avatar.
    avatar_dna JSON NULL,

    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_avatar_usuario (id_usuario),

    CONSTRAINT fk_avatar_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuarios(id_usuario)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 4. CATALOGO + ARMARIO DEL USUARIO
--
-- prendas.id_usuario IS NULL  = catalogo de FitAI
-- prendas.id_usuario IS NOT NULL = prenda del usuario
--
-- Se mantiene este modelo porque es compatible con el backend
-- actual y permite que una compra pase al armario del usuario.
-- ============================================================

CREATE TABLE IF NOT EXISTS prendas (
    id_prenda INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    id_usuario INT UNSIGNED NULL,

    nombre_prenda VARCHAR(150) NOT NULL,
    categoria VARCHAR(50) NOT NULL DEFAULT 'otro',
    subcategoria VARCHAR(50) NULL,

    color VARCHAR(50) NULL,
    talla VARCHAR(20) NULL,
    estilo VARCHAR(50) NULL,
    temporada VARCHAR(30) NULL,

    marca VARCHAR(100) NULL,
    descripcion TEXT NULL,

    url_imagen VARCHAR(500) NULL,

    -- Precio del catalogo. Para prendas del armario puede conservar
    -- el precio historico de compra.
    precio DECIMAL(12,2) NULL,

    stock INT UNSIGNED NULL,
    activo TINYINT(1) NOT NULL DEFAULT 1,

    fecha_subida TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_prendas_usuario (id_usuario),
    INDEX idx_prendas_categoria (categoria),
    INDEX idx_prendas_estilo (estilo),
    INDEX idx_prendas_catalogo (id_usuario, activo),
    INDEX idx_prendas_nombre (nombre_prenda),

    CONSTRAINT fk_prendas_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuarios(id_usuario)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 5. OUTFITS
-- ============================================================

CREATE TABLE IF NOT EXISTS outfits (
    id_outfit INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT UNSIGNED NOT NULL,

    nombre VARCHAR(100) NOT NULL,
    descripcion TEXT NULL,
    creado_por VARCHAR(30) NOT NULL DEFAULT 'usuario',

    favorito TINYINT(1) NOT NULL DEFAULT 0,

    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_outfits_usuario (id_usuario),
    INDEX idx_outfits_favorito (id_usuario, favorito),

    CONSTRAINT fk_outfits_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuarios(id_usuario)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS outfit_prendas (
    id_outfit INT UNSIGNED NOT NULL,
    id_prenda INT UNSIGNED NOT NULL,

    PRIMARY KEY (id_outfit, id_prenda),

    INDEX idx_outfit_prendas_prenda (id_prenda),

    CONSTRAINT fk_outfit_prendas_outfit
        FOREIGN KEY (id_outfit)
        REFERENCES outfits(id_outfit)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_outfit_prendas_prenda
        FOREIGN KEY (id_prenda)
        REFERENCES prendas(id_prenda)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 6. PRUEBAS VIRTUALES
-- ============================================================

CREATE TABLE IF NOT EXISTS pruebas_virtuales (
    id_prueba INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT UNSIGNED NOT NULL,
    id_outfit INT UNSIGNED NULL,

    tipo_prueba VARCHAR(50) NULL,
    url_resultado VARCHAR(500) NULL,

    -- Resultado/metadatos de IA si se necesitan posteriormente.
    datos_resultado JSON NULL,

    fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_pruebas_usuario (id_usuario),
    INDEX idx_pruebas_outfit (id_outfit),

    CONSTRAINT fk_pruebas_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuarios(id_usuario)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_pruebas_outfit
        FOREIGN KEY (id_outfit)
        REFERENCES outfits(id_outfit)
        ON DELETE SET NULL
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 7. ANALISIS CORPORALES DE IA
-- ============================================================

CREATE TABLE IF NOT EXISTS analisis_corporales (
    id_analisis INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT UNSIGNED NOT NULL,
    id_foto INT UNSIGNED NULL,

    altura_referencia DECIMAL(6,2) NULL,

    -- Resultado completo de MediaPipe/IA.
    resultado JSON NULL,

    detectado TINYINT(1) NOT NULL DEFAULT 0,
    fecha_analisis TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_analisis_usuario (id_usuario),
    INDEX idx_analisis_fecha (id_usuario, fecha_analisis),

    CONSTRAINT fk_analisis_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuarios(id_usuario)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_analisis_foto
        FOREIGN KEY (id_foto)
        REFERENCES fotos_usuario(id_foto)
        ON DELETE SET NULL
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 8. SUGERENCIAS DE IA
-- ============================================================

CREATE TABLE IF NOT EXISTS sugerencias_ia (
    id_sugerencia INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT UNSIGNED NOT NULL,

    tipo_evento VARCHAR(50) NULL,
    clima VARCHAR(100) NULL,
    ocasion VARCHAR(100) NULL,
    estilo VARCHAR(100) NULL,

    descripcion TEXT NULL,

    -- Permite guardar recomendaciones estructuradas sin cambiar
    -- la tabla cada vez que evolucionen los modelos de IA.
    datos JSON NULL,

    fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_sugerencias_usuario (id_usuario),
    INDEX idx_sugerencias_fecha (id_usuario, fecha),

    CONSTRAINT fk_sugerencias_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuarios(id_usuario)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 9. HISTORIAL DEL ASISTENTE / IA
-- ============================================================

CREATE TABLE IF NOT EXISTS consultas_ia (
    id_consulta BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT UNSIGNED NULL,

    tipo VARCHAR(50) NOT NULL DEFAULT 'asistente',
    pagina VARCHAR(100) NULL,

    mensaje TEXT NOT NULL,
    respuesta TEXT NULL,

    fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_consultas_usuario (id_usuario),
    INDEX idx_consultas_fecha (fecha),

    CONSTRAINT fk_consultas_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuarios(id_usuario)
        ON DELETE SET NULL
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 10. CARRITO
-- ============================================================

CREATE TABLE IF NOT EXISTS carrito (
    id_carrito INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT UNSIGNED NOT NULL,
    id_prenda INT UNSIGNED NOT NULL,

    cantidad INT UNSIGNED NOT NULL DEFAULT 1,

    fecha_agregado TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_carrito_usuario_prenda (id_usuario, id_prenda),
    INDEX idx_carrito_usuario (id_usuario),

    CONSTRAINT fk_carrito_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuarios(id_usuario)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_carrito_prenda
        FOREIGN KEY (id_prenda)
        REFERENCES prendas(id_prenda)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 11. PEDIDOS
-- ============================================================

CREATE TABLE IF NOT EXISTS pedidos (
    id_pedido BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT UNSIGNED NOT NULL,

    total DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    moneda CHAR(3) NOT NULL DEFAULT 'COP',

    estado VARCHAR(30) NOT NULL DEFAULT 'pendiente',
    estado_pago VARCHAR(30) NOT NULL DEFAULT 'pendiente',

    referencia_externa VARCHAR(150) NULL,

    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_pedidos_usuario (id_usuario),
    INDEX idx_pedidos_estado (estado),
    INDEX idx_pedidos_pago (estado_pago),
    INDEX idx_pedidos_fecha (fecha_creacion),

    CONSTRAINT fk_pedidos_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuarios(id_usuario)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS pedido_detalles (
    id_detalle BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_pedido BIGINT UNSIGNED NOT NULL,

    -- Se conserva el ID de la prenda del catalogo como referencia
    -- historica. Los datos de nombre/precio quedan congelados aqui
    -- para que un pedido no cambie si luego cambia el catalogo.
    id_prenda_catalogo INT UNSIGNED NULL,

    nombre_prenda VARCHAR(150) NOT NULL,
    categoria VARCHAR(50) NULL,
    talla VARCHAR(20) NULL,
    color VARCHAR(50) NULL,

    precio DECIMAL(12,2) NOT NULL,
    cantidad INT UNSIGNED NOT NULL DEFAULT 1,
    subtotal DECIMAL(12,2) NOT NULL DEFAULT 0.00,

    INDEX idx_detalle_pedido (id_pedido),
    INDEX idx_detalle_prenda (id_prenda_catalogo),

    CONSTRAINT fk_detalle_pedido
        FOREIGN KEY (id_pedido)
        REFERENCES pedidos(id_pedido)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 12. PAGOS
--
-- Preparada para Wompi/Mercado Pago/Stripe u otro proveedor.
-- Actualmente el backend puede registrar pedidos sin pasarela.
-- ============================================================

CREATE TABLE IF NOT EXISTS pagos (
    id_pago BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_pedido BIGINT UNSIGNED NOT NULL,

    proveedor VARCHAR(50) NULL,
    referencia_pago VARCHAR(150) NULL,

    monto DECIMAL(12,2) NOT NULL,
    moneda CHAR(3) NOT NULL DEFAULT 'COP',

    estado VARCHAR(30) NOT NULL DEFAULT 'pendiente',
    metodo VARCHAR(50) NULL,

    datos_respuesta JSON NULL,

    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_pago_referencia (proveedor, referencia_pago),
    INDEX idx_pagos_pedido (id_pedido),
    INDEX idx_pagos_estado (estado),

    CONSTRAINT fk_pagos_pedido
        FOREIGN KEY (id_pedido)
        REFERENCES pedidos(id_pedido)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 13. CONTACTO
-- ============================================================

CREATE TABLE IF NOT EXISTS contactos (
    id_contacto INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(190) NOT NULL,
    asunto VARCHAR(150) NOT NULL,
    mensaje TEXT NOT NULL,

    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_contactos_fecha (fecha_creacion),
    INDEX idx_contactos_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 14. CATALOGO INICIAL
--
-- id_usuario = NULL => producto oficial de FitAI.
-- No se duplica si el script se ejecuta otra vez.
-- ============================================================

INSERT INTO prendas
    (id_usuario, nombre_prenda, categoria, color, talla, estilo,
     temporada, url_imagen, precio, stock, activo)
SELECT
    NULL, 'Camiseta Básica Pima', 'Casual', 'Blanco', 'M', 'casual',
    'todo', 'img/ava.jpg', 25.00, 100, 1
WHERE NOT EXISTS (
    SELECT 1 FROM prendas
    WHERE id_usuario IS NULL
      AND nombre_prenda = 'Camiseta Básica Pima'
);

INSERT INTO prendas
    (id_usuario, nombre_prenda, categoria, color, talla, estilo,
     temporada, url_imagen, precio, stock, activo)
SELECT
    NULL, 'Jeans Slim Fit', 'Casual', 'Azul Oscuro', '32', 'casual',
    'todo', 'img/avaratare.jpg', 45.00, 100, 1
WHERE NOT EXISTS (
    SELECT 1 FROM prendas
    WHERE id_usuario IS NULL
      AND nombre_prenda = 'Jeans Slim Fit'
);

INSERT INTO prendas
    (id_usuario, nombre_prenda, categoria, color, talla, estilo,
     temporada, url_imagen, precio, stock, activo)
SELECT
    NULL, 'Chaqueta Denim Vintage', 'Casual', 'Celeste', 'L', 'casual',
    'todo', 'img/avat.jpg', 60.00, 100, 1
WHERE NOT EXISTS (
    SELECT 1 FROM prendas
    WHERE id_usuario IS NULL
      AND nombre_prenda = 'Chaqueta Denim Vintage'
);

INSERT INTO prendas
    (id_usuario, nombre_prenda, categoria, color, talla, estilo,
     temporada, url_imagen, precio, stock, activo)
SELECT
    NULL, 'Blazer Formal Fit', 'Formal', 'Negro', 'M', 'formal',
    'todo', 'img/avata.jpg', 85.00, 100, 1
WHERE NOT EXISTS (
    SELECT 1 FROM prendas
    WHERE id_usuario IS NULL
      AND nombre_prenda = 'Blazer Formal Fit'
);

INSERT INTO prendas
    (id_usuario, nombre_prenda, categoria, color, talla, estilo,
     temporada, url_imagen, precio, stock, activo)
SELECT
    NULL, 'Camisa Oxford Premium', 'Formal', 'Azul Claro', 'S', 'formal',
    'todo', 'img/avatar.jpg', 35.00, 100, 1
WHERE NOT EXISTS (
    SELECT 1 FROM prendas
    WHERE id_usuario IS NULL
      AND nombre_prenda = 'Camisa Oxford Premium'
);

INSERT INTO prendas
    (id_usuario, nombre_prenda, categoria, color, talla, estilo,
     temporada, url_imagen, precio, stock, activo)
SELECT
    NULL, 'Pantalón de Vestir Sastre', 'Formal', 'Gris Oxford', '30', 'formal',
    'todo', 'img/modelo.jpg', 50.00, 100, 1
WHERE NOT EXISTS (
    SELECT 1 FROM prendas
    WHERE id_usuario IS NULL
      AND nombre_prenda = 'Pantalón de Vestir Sastre'
);

INSERT INTO prendas
    (id_usuario, nombre_prenda, categoria, color, talla, estilo,
     temporada, url_imagen, precio, stock, activo)
SELECT
    NULL, 'Jogger Deportivo Tech', 'Deportivo', 'Gris Melange', 'M', 'deportivo',
    'todo', 'img/ava.jpg', 30.00, 100, 1
WHERE NOT EXISTS (
    SELECT 1 FROM prendas
    WHERE id_usuario IS NULL
      AND nombre_prenda = 'Jogger Deportivo Tech'
);

INSERT INTO prendas
    (id_usuario, nombre_prenda, categoria, color, talla, estilo,
     temporada, url_imagen, precio, stock, activo)
SELECT
    NULL, 'Camiseta Deportiva Transpirable', 'Deportivo', 'Negro', 'L', 'deportivo',
    'todo', 'img/avaratare.jpg', 20.00, 100, 1
WHERE NOT EXISTS (
    SELECT 1 FROM prendas
    WHERE id_usuario IS NULL
      AND nombre_prenda = 'Camiseta Deportiva Transpirable'
);

INSERT INTO prendas
    (id_usuario, nombre_prenda, categoria, color, talla, estilo,
     temporada, url_imagen, precio, stock, activo)
SELECT
    NULL, 'Rompevientos Ligero', 'Deportivo', 'Verde Oliva', 'XL', 'deportivo',
    'todo', 'img/avat.jpg', 55.00, 100, 1
WHERE NOT EXISTS (
    SELECT 1 FROM prendas
    WHERE id_usuario IS NULL
      AND nombre_prenda = 'Rompevientos Ligero'
);


SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- FIN DEL ESQUEMA UNICO DE FITAI STYLE
-- ============================================================

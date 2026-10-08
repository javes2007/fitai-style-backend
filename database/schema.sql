-- ============================================================
-- FitAI Style — esquema inicial de MySQL
-- Ejecutar dentro de la base de datos indicada por DB_NAME.
-- ============================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(190) NOT NULL UNIQUE,
    contrasena VARCHAR(255) NOT NULL,
    altura DECIMAL(6,2) NULL,
    ancho_hombros DECIMAL(6,2) NULL,
    pecho DECIMAL(6,2) NULL,
    cintura DECIMAL(6,2) NULL,
    cadera DECIMAL(6,2) NULL,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS prendas (
    id_prenda INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NULL,
    nombre_prenda VARCHAR(100) NOT NULL,
    categoria VARCHAR(50) NOT NULL,
    color VARCHAR(50) NULL,
    talla VARCHAR(20) NULL,
    estilo VARCHAR(50) NULL,
    temporada VARCHAR(30) NULL,
    url_imagen VARCHAR(500) NULL,
    precio DECIMAL(12,2) NULL,
    fecha_subida TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_prendas_usuario (id_usuario),
    INDEX idx_prendas_categoria (categoria),
    CONSTRAINT fk_prendas_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS outfits (
    id_outfit INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    creado_por VARCHAR(30) NOT NULL DEFAULT 'usuario',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_outfits_usuario (id_usuario),
    CONSTRAINT fk_outfits_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS outfit_prendas (
    id_outfit INT NOT NULL,
    id_prenda INT NOT NULL,
    PRIMARY KEY (id_outfit, id_prenda),
    CONSTRAINT fk_outfit_prendas_outfit
        FOREIGN KEY (id_outfit) REFERENCES outfits(id_outfit)
        ON DELETE CASCADE,
    CONSTRAINT fk_outfit_prendas_prenda
        FOREIGN KEY (id_prenda) REFERENCES prendas(id_prenda)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS contactos (
    id_contacto INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(190) NOT NULL,
    asunto VARCHAR(150) NOT NULL,
    mensaje TEXT NOT NULL,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_contactos_fecha (fecha_creacion)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS avatar_perfiles (
    id_avatar INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL UNIQUE,
    edad INT NULL,
    estilo VARCHAR(50) NULL,
    cuerpo JSON NULL,
    rostro JSON NULL,
    cabello JSON NULL,
    estetica JSON NULL,
    foto_analizada BOOLEAN NOT NULL DEFAULT FALSE,
    avatar_dna JSON NULL,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_avatar_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS carrito (
    id_carrito INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,
    id_prenda INT NOT NULL,
    cantidad INT NOT NULL DEFAULT 1,
    fecha_agregado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_carrito_usuario_prenda (id_usuario, id_prenda),
    INDEX idx_carrito_usuario (id_usuario),
    CONSTRAINT fk_carrito_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
        ON DELETE CASCADE,
    CONSTRAINT fk_carrito_prenda
        FOREIGN KEY (id_prenda) REFERENCES prendas(id_prenda)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS pedidos (
    id_pedido INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,
    total DECIMAL(12,2) NOT NULL DEFAULT 0,
    estado VARCHAR(30) NOT NULL DEFAULT 'pendiente',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_pedidos_usuario (id_usuario),
    CONSTRAINT fk_pedidos_usuario
        FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS pedido_detalles (
    id_detalle INT AUTO_INCREMENT PRIMARY KEY,
    id_pedido INT NOT NULL,
    id_prenda_catalogo INT NOT NULL,
    nombre_prenda VARCHAR(100) NOT NULL,
    precio DECIMAL(12,2) NOT NULL,
    cantidad INT NOT NULL DEFAULT 1,
    INDEX idx_detalle_pedido (id_pedido),
    CONSTRAINT fk_detalle_pedido
        FOREIGN KEY (id_pedido) REFERENCES pedidos(id_pedido)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Catálogo inicial de FitAI. id_usuario = NULL significa producto del catálogo.
INSERT INTO prendas
    (id_usuario,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio)
SELECT NULL,'Camiseta Básica Pima','Casual','Blanco','M','casual','todo','img/ava.jpg',25.00
WHERE NOT EXISTS (SELECT 1 FROM prendas WHERE id_usuario IS NULL);

INSERT INTO prendas
    (id_usuario,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio)
SELECT NULL,'Jeans Slim Fit','Casual','Azul Oscuro','32','casual','todo','img/avaratare.jpg',45.00
WHERE NOT EXISTS (SELECT 1 FROM prendas WHERE id_usuario IS NULL AND nombre_prenda='Jeans Slim Fit');

INSERT INTO prendas
    (id_usuario,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio)
SELECT NULL,'Chaqueta Denim Vintage','Casual','Celeste','L','casual','todo','img/avat.jpg',60.00
WHERE NOT EXISTS (SELECT 1 FROM prendas WHERE id_usuario IS NULL AND nombre_prenda='Chaqueta Denim Vintage');

INSERT INTO prendas
    (id_usuario,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio)
SELECT NULL,'Blazer Formal Fit','Formal','Negro','M','formal','todo','img/avata.jpg',85.00
WHERE NOT EXISTS (SELECT 1 FROM prendas WHERE id_usuario IS NULL AND nombre_prenda='Blazer Formal Fit');

INSERT INTO prendas
    (id_usuario,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio)
SELECT NULL,'Camisa Oxford Premium','Formal','Azul Claro','S','formal','todo','img/avatar.jpg',35.00
WHERE NOT EXISTS (SELECT 1 FROM prendas WHERE id_usuario IS NULL AND nombre_prenda='Camisa Oxford Premium');

INSERT INTO prendas
    (id_usuario,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio)
SELECT NULL,'Pantalón de Vestir Sastre','Formal','Gris Oxford','30','formal','todo','img/modelo.jpg',50.00
WHERE NOT EXISTS (SELECT 1 FROM prendas WHERE id_usuario IS NULL AND nombre_prenda='Pantalón de Vestir Sastre');

INSERT INTO prendas
    (id_usuario,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio)
SELECT NULL,'Jogger Deportivo Tech','Deportivo','Gris Melange','M','deportivo','todo','img/ava.jpg',30.00
WHERE NOT EXISTS (SELECT 1 FROM prendas WHERE id_usuario IS NULL AND nombre_prenda='Jogger Deportivo Tech');

INSERT INTO prendas
    (id_usuario,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio)
SELECT NULL,'Camiseta Deportiva Transpirable','Deportivo','Negro','L','deportivo','todo','img/avaratare.jpg',20.00
WHERE NOT EXISTS (SELECT 1 FROM prendas WHERE id_usuario IS NULL AND nombre_prenda='Camiseta Deportiva Transpirable');

INSERT INTO prendas
    (id_usuario,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio)
SELECT NULL,'Rompevientos Ligero','Deportivo','Verde Oliva','XL','deportivo','todo','img/avat.jpg',55.00
WHERE NOT EXISTS (SELECT 1 FROM prendas WHERE id_usuario IS NULL AND nombre_prenda='Rompevientos Ligero');

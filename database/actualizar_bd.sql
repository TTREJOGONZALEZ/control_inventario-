-- Ejecuta este archivo UNA SOLA VEZ, sobre la base panel_tienda ya importada.
-- NO borra negocios, usuarios, ventas ni productos existentes.
USE panel_tienda;
ALTER TABLE productos
    ADD COLUMN costo_compra DECIMAL(10,2) NULL
    COMMENT 'Costo unitario actual; NULL significa no registrado';

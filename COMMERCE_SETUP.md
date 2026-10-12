# Puesta en marcha de compras FitAI Style

## 1. Primero usa el modo de pruebas

En Render, configura las variables del archivo .env.example en Environment. No publiques secretos en GitHub ni en JavaScript.

- MERCADOPAGO_ACCESS_TOKEN: token de prueba de Mercado Pago (TEST-...) durante la validación.
- PUBLIC_BACKEND_URL: URL HTTPS real del backend.
- FRONTEND_URL: URL HTTPS real del frontend.
- WOMPI_PUBLIC_KEY, WOMPI_PRIVATE_KEY y WOMPI_INTEGRITY_SECRET: llaves de prueba de tu comercio Wompi.
- FITAI_MIN_CHECKOUT_COP=1000: bloquea los precios de demostración actuales (25, 35, 45, etc.).
- STORE_ADMIN_TOKEN: token aleatorio largo para crear/actualizar precios e inventario; úsalo solo desde Postman/curl.

En el panel de Mercado Pago registra:
https://TU-BACKEND.onrender.com/api/pagos/webhook/mercadopago

En el panel de Wompi registra:
https://TU-BACKEND.onrender.com/api/pagos/webhook/wompi

Wompi usa el entorno de pruebas si la llave privada comienza con prv_test_; en producción usa la llave privada de producción. No mezcles llaves de prueba y producción.

## 2. Confirma precios e inventario antes de vender

El catálogo inicial contiene precios de demostración. El checkout rechaza esos precios y no permite comprar sin stock configurado.

Ver productos: GET /api/tienda/catalogo?limite=100

Crear una prenda de tienda (con precio real en COP y stock inicial):

    curl -X POST "https://TU-BACKEND.onrender.com/api/tienda/admin/productos" \
      -H "Content-Type: application/json" \
      -H "X-Store-Admin-Token: TU_STORE_ADMIN_TOKEN" \
      -d '{
        "nombre": "Camiseta de prueba",
        "categoria": "Casual",
        "color": "Azul",
        "talla": "M",
        "estilo": "casual",
        "temporada": "todo",
        "url_imagen": "https://URL-REAL-DE-IMAGEN",
        "precio": 50000,
        "stock": 5
      }'

El precio del ejemplo es solo ilustrativo: cámbialo por el precio real que cobrarás. Para actualizar una prenda existente del catálogo:

    curl -X PATCH "https://TU-BACKEND.onrender.com/api/tienda/admin/productos/ID_PRENDA" \
      -H "Content-Type: application/json" \
      -H "X-Store-Admin-Token: TU_STORE_ADMIN_TOKEN" \
      -d '{"precio": 50000, "stock": 5, "activo": true}'

## 3. Qué se integra

- La tienda propia usa catálogo, precio en COP e inventario gestionados en el backend.
- El carrito valida disponibilidad y el checkout reserva stock, impide cobros duplicados, guarda snapshots de la prenda y elimina solo las unidades del carrito incluidas en el pedido.
- Mercado Pago y Wompi confirman el pago mediante consulta servidor-a-servidor. Un parámetro de retorno del navegador no se toma como prueba de pago.
- Mercado Libre muestra resultados reales de su búsqueda pública Colombia. Amazon, SHEIN y Temu abren búsquedas externas; para mostrar catálogo/afiliación dentro de FitAI se requiere acceso oficial y autorización de la cuenta. Referencias: Amazon Creators API https://affiliate-program.amazon.com/creatorsapi/docs/en-us/onboarding, afiliados SHEIN https://www.shein.com.co/affiliate-a-427.html, Temu Partner https://partner-us.temu.com/.

## 4. Pruebas obligatorias antes de producción

1. Probar catálogo, imágenes, inicio de sesión y carrito en escritorio y móvil.
2. Confirmar que un producto con precio de demostración o stock cero no se puede comprar.
3. Doble clic en checkout: debe reutilizar el checkout pendiente o rechazar el segundo intento.
4. Cambiar el carrito mientras el pago está pendiente: el pago debe retirar solo las unidades de la instantánea, no los artículos añadidos después.
5. Probar pago aprobado, rechazado, cancelado y notificaciones repetidas.
6. Simular caída de base de datos durante un webhook y comprobar que la pasarela recibe un error reintentable.
7. Revisar políticas de privacidad, términos, soporte y el proceso de devolución antes de activar cobros reales.

La compilación de sintaxis no reemplaza estas pruebas con credenciales sandbox y una base de datos de pruebas.
